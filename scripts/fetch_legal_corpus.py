import hashlib
import html
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from backend.core.config import PROJECT_ROOT
from backend.src.store import now_iso
from src.rag.core import chunk_segments, normalize_vietnamese

MAX_DOCUMENT_CHARS = 600_000
MAX_TOTAL_CHARS = 8_000_000


def html_to_text(value: str) -> str:
    value = re.sub(r"<!--[\s\S]*?-->", " ", value)
    value = re.sub(r"<(script|style|head)\b[^>]*>[\s\S]*?</\1\s*>", " ", value, flags=re.I)
    value = re.sub(r"<br\s*/?\s*>", "\n", value, flags=re.I)
    value = re.sub(
        r"</\s*(?:p|div|li|tr|td|th|h[1-6]|table|section|article)\s*>", "\n", value, flags=re.I
    )
    value = re.sub(r"<li\b[^>]*>", "• ", value, flags=re.I)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", value)
    return normalize_vietnamese(re.sub(r" *\n *", "\n", value))


def fetch_json(client, url):
    for attempt in range(4):
        try:
            response = client.get(url)
            if response.status_code in {408, 429} or response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 3:
                raise
            time.sleep(min(10, 0.75 * 2**attempt))
    raise RuntimeError("No public API response")


def clean_part(value, fallback=""):
    return normalize_vietnamese(value if isinstance(value, str) else "")[:500] or fallback


def date_only(value):
    matched = re.match(r"\d{4}-\d{2}-\d{2}", value) if isinstance(value, str) else None
    return matched[0] if matched else None


def build_document(client, entry, generated_at):
    payload = fetch_json(
        client, f"https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/{entry['id']}"
    )
    if not payload.get("success") or not isinstance(payload.get("data"), dict):
        raise ValueError("No public document")
    document = payload["data"]
    number = clean_part(document.get("docNum"))
    if number.lower() != entry["expected"].lower():
        raise ValueError("Document number differs from curated selection")
    body = html_to_text(document.get("documentContent", {}).get("content", ""))
    if not 500 <= len(body) <= MAX_DOCUMENT_CHARS:
        raise ValueError("Document is outside safe size limits")
    source_id = f"vbpl-{entry['id']}"
    legal_type = clean_part(
        (document.get("docType") or {}).get("name"), "Văn bản quy phạm pháp luật"
    )
    title = clean_part(document.get("title"), number)
    status = [
        clean_part(
            (document.get("effStatus") or {}).get("name"), "Chưa có dữ liệu trạng thái từ VBPL"
        )
    ]
    for field, label in (("effFrom", "hiệu lực từ"), ("effTo", "đến")):
        date = date_only(document.get(field))
        if date:
            status.append(f"{label} {date}")
    chunks = [
        {
            **{
                key: chunk[key]
                for key in ("id", "ordinal", "locator", "heading", "text", "checksum")
            },
            "sourceId": source_id,
        }
        for chunk in chunk_segments(source_id, [{"locator": "Toàn văn", "text": body}])
    ]
    source = {
        "id": source_id,
        "name": " · ".join(part for part in (legal_type, number, title) if part),
        "kind": "legal-document",
        "mimeType": "text/html",
        "byteSize": len(body.encode()),
        "status": "ready",
        "chunkCount": len(chunks),
        "sourceUrl": f"https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID={entry['id']}",
        "legalType": legal_type,
        "legalArea": ", ".join(
            clean_part(field.get("name")) for field in document.get("documentFields") or []
        )
        or None,
        "documentNumber": number,
        "issuingAuthority": clean_part(
            document.get("agencyName") or (document.get("organization") or {}).get("name")
        )
        or None,
        "issueDate": date_only(document.get("issueDate")),
        "effectiveStatus": " · ".join(status),
        "sourceContentHash": hashlib.sha256(body.encode()).hexdigest(),
        "bodySource": "vbpl-public-gateway",
        "selectionGroup": entry["group"],
        "builtin": True,
        "createdAt": generated_at,
    }
    return source, chunks, len(body)


def build(output: Path = PROJECT_ROOT / "data/legal-corpus.json"):
    config = json.loads((PROJECT_ROOT / "config/legal-corpus.json").read_text(encoding="utf-8"))
    generated_at = now_iso()
    with httpx.Client(
        timeout=25,
        headers={"accept": "application/json", "user-agent": "LuatRAG-corpus-builder/2.0"},
    ) as client:
        revision = fetch_json(
            client,
            f"https://huggingface.co/api/datasets/{config['dataset']}/revision/{config['revision']}",
        )
        if revision.get("sha") != config["revision"]:
            raise ValueError("Pinned dataset revision could not be verified")

        def worker(entry):
            try:
                return build_document(client, entry, generated_at)
            except Exception as error:
                return str(error)[:240]

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(worker, config["documents"]))
    documents, chunks, failed = [], [], []
    total = 0
    for entry, result in zip(config["documents"], results, strict=True):
        if isinstance(result, str):
            failed.append({"id": entry["id"], "reason": result})
            continue
        source, parts, count = result
        if total + count > MAX_TOTAL_CHARS:
            failed.append({"id": entry["id"], "reason": "Vượt tổng dung lượng corpus an toàn"})
            continue
        documents.append(source)
        chunks.extend(parts)
        total += count
    if len(documents) < 24 or len(chunks) < 150:
        raise ValueError("Refusing to overwrite corpus below minimum breadth thresholds")
    if len({source["id"] for source in documents}) != len(documents) or len(
        {chunk["id"] for chunk in chunks}
    ) != len(chunks):
        raise ValueError("Duplicate corpus identifiers")
    manifest = json.loads(output.read_text(encoding="utf-8"))["manifest"]
    manifest.pop("artifactSha256", None)
    manifest.update(
        {
            "revision": config["revision"],
            "generatedAt": generated_at,
            "snapshotDate": generated_at[:10],
            "selection": {
                **manifest["selection"],
                "requestedItemIds": [entry["id"] for entry in config["documents"]],
                "includedItemIds": [int(source["id"][5:]) for source in documents],
                "failed": failed,
                "repositoryRevisionVerified": True,
                "maxDocumentChars": MAX_DOCUMENT_CHARS,
                "maxTotalChars": MAX_TOTAL_CHARS,
            },
        }
    )
    artifact = {"manifest": manifest, "documents": documents, "chunks": chunks}
    canonical = json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
    manifest["artifactSha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    with tempfile.NamedTemporaryFile(
        dir=output.parent, mode="w", encoding="utf-8", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(
        {
            "documents": len(documents),
            "chunks": len(chunks),
            "characters": total,
            "failed": len(failed),
        }
    )


if __name__ == "__main__":
    build()
