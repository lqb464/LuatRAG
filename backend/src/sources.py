import hashlib
import json
from uuid import uuid4

from backend.core.security import ServiceError, clean_filename
from backend.src.store import encode_json, now_iso
from src.rag.core import chunk_segments
from src.rag.documents import EXTENSION_KIND, extract_document, validated_segments


def source_from_row(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "mimeType": row["mime_type"],
        "byteSize": row["byte_size"],
        "status": row["status"],
        "chunkCount": row["chunk_count"],
        "sourceUrl": row["source_url"],
        "builtin": False,
        "createdAt": row["created_at"],
    }


def list_sources(store, corpus, owner_id: str) -> list[dict]:
    with store.connect() as db:
        rows = db.execute(
            "SELECT * FROM sources WHERE owner_id = ? AND status != 'deleting' ORDER BY created_at DESC LIMIT 100",
            (owner_id,),
        ).fetchall()
    return [*corpus.sources, *(source_from_row(row) for row in rows)]


def insert_chunks(db, chunks: list[dict], source_id: str, owner_id: str, now: str):
    db.executemany(
        """INSERT INTO chunks (id, source_id, owner_id, ordinal, locator, heading, text, text_folded, checksum, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                chunk["id"],
                source_id,
                owner_id,
                chunk["ordinal"],
                chunk["locator"],
                chunk["heading"],
                chunk["text"],
                chunk["textFolded"],
                chunk["checksum"],
                now,
            )
            for chunk in chunks
        ],
    )


def safe_chunks(source_id: str, segments: list[dict]) -> list[dict]:
    chunks = chunk_segments(source_id, segments)
    if not 1 <= len(chunks) <= 1800:
        raise ServiceError(
            422, "invalid_chunk_count", "Không thể chia tài liệu thành các đoạn an toàn."
        )
    return chunks


def create_source(store, owner_id: str, filename: str, mime_type: str, value: bytes) -> dict:
    name = clean_filename(filename)
    if not name:
        raise ServiceError(400, "invalid_filename", "Tên tệp không hợp lệ.")
    segments, parser = extract_document(name, value)
    source_id, now = str(uuid4()), now_iso()
    chunks = safe_chunks(source_id, segments)
    kind = EXTENSION_KIND[name.rsplit(".", 1)[-1].lower()]
    original_key = f"users/{owner_id}/sources/{source_id}/original/{name}"
    extracted_key = f"users/{owner_id}/sources/{source_id}/extracted.json"
    keys = [original_key, extracted_key]
    try:
        store.put_object(original_key, value)
        store.put_object(
            extracted_key, encode_json({"segments": segments, "parser": parser}).encode()
        )
        with store.connect(write=True) as db:
            db.execute(
                """INSERT INTO sources (id, owner_id, name, kind, mime_type, byte_size, sha256, r2_key, extracted_key, status, chunk_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?)""",
                (
                    source_id,
                    owner_id,
                    name,
                    kind,
                    mime_type or "application/octet-stream",
                    len(value),
                    hashlib.sha256(value).hexdigest(),
                    original_key,
                    extracted_key,
                    len(chunks),
                    now,
                    now,
                ),
            )
            insert_chunks(db, chunks, source_id, owner_id, now)
            store.audit(
                db,
                owner_id,
                "source.created",
                source_id,
                {
                    "name": name,
                    "kind": kind,
                    "byteSize": len(value),
                    "chunkCount": len(chunks),
                    "parser": parser,
                },
            )
    except BaseException:
        for key in keys:
            store.delete_object(key)
        raise
    return {
        "id": source_id,
        "name": name,
        "kind": kind,
        "mimeType": mime_type or "application/octet-stream",
        "byteSize": len(value),
        "status": "ready",
        "chunkCount": len(chunks),
        "builtin": False,
        "createdAt": now,
    }


def delete_source(store, owner_id: str, source_id: str):
    with store.connect(write=True) as db:
        row = db.execute(
            "SELECT r2_key, extracted_key FROM sources WHERE id = ? AND owner_id = ?",
            (source_id, owner_id),
        ).fetchone()
        if not row:
            raise ServiceError(404, "source_not_found", "Không tìm thấy nguồn.")
        db.execute(
            "UPDATE sources SET status = 'deleting' WHERE id = ? AND owner_id = ?",
            (source_id, owner_id),
        )
    keys = [key for key in (row["r2_key"], row["extracted_key"]) if key]
    objects_deleted = False
    try:
        for key in keys:
            store.delete_object(key)
        objects_deleted = True
        with store.connect(write=True) as db:
            db.execute(
                """DELETE FROM conversations WHERE owner_id = ? AND id IN (
                SELECT DISTINCT messages.conversation_id FROM messages, json_each(messages.evidence_json)
                WHERE messages.owner_id = ? AND messages.evidence_json IS NOT NULL
                AND json_extract(json_each.value, '$.sourceId') = ?)""",
                (owner_id, owner_id, source_id),
            )
            db.execute("DELETE FROM sources WHERE id = ? AND owner_id = ?", (source_id, owner_id))
            store.audit(db, owner_id, "source.deleted", source_id, {})
    except BaseException:
        with store.connect(write=True) as db:
            db.execute(
                "UPDATE sources SET status = ?, error_code = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
                (
                    "error" if objects_deleted else "ready",
                    "delete_database_failed" if objects_deleted else None,
                    now_iso(),
                    source_id,
                    owner_id,
                ),
            )
        raise


def reindex_source(store, owner_id: str, source_id: str) -> int:
    with store.connect() as db:
        row = db.execute(
            "SELECT extracted_key FROM sources WHERE id = ? AND owner_id = ?", (source_id, owner_id)
        ).fetchone()
    if not row or not row["extracted_key"]:
        raise ServiceError(404, "source_not_found", "Không tìm thấy nguồn có thể lập chỉ mục.")
    value = store.get_object(row["extracted_key"])
    if value is None:
        raise ServiceError(410, "extraction_missing", "Bản trích xuất không còn tồn tại.")
    segments = validated_segments(json.loads(value).get("segments"))
    chunks = safe_chunks(source_id, segments)
    now = now_iso()
    with store.connect(write=True) as db:
        exists = db.execute(
            "SELECT 1 FROM sources WHERE id = ? AND owner_id = ?", (source_id, owner_id)
        ).fetchone()
        if not exists:
            raise ServiceError(404, "source_not_found", "Không tìm thấy nguồn.")
        db.execute("DELETE FROM chunks WHERE source_id = ? AND owner_id = ?", (source_id, owner_id))
        insert_chunks(db, chunks, source_id, owner_id, now)
        db.execute(
            "UPDATE sources SET status = 'ready', chunk_count = ?, error_code = NULL, updated_at = ? WHERE id = ? AND owner_id = ?",
            (len(chunks), now, source_id, owner_id),
        )
        store.audit(db, owner_id, "source.reindexed", source_id, {"chunkCount": len(chunks)})
    return len(chunks)


def source_evidence(store, corpus, owner_id: str, source_id: str) -> list[dict]:
    builtin = [chunk for chunk in corpus.chunks if chunk["sourceId"] == source_id]
    if builtin:
        return builtin[:100]
    with store.connect() as db:
        source = db.execute(
            "SELECT name, source_url FROM sources WHERE id = ? AND owner_id = ?",
            (source_id, owner_id),
        ).fetchone()
        if not source:
            raise ServiceError(404, "source_not_found", "Không tìm thấy nguồn.")
        rows = db.execute(
            "SELECT id, locator, heading, text FROM chunks WHERE source_id = ? AND owner_id = ? ORDER BY ordinal LIMIT 100",
            (source_id, owner_id),
        ).fetchall()
    return [
        {
            **dict(row),
            "sourceId": source_id,
            "sourceName": source["name"],
            "sourceUrl": source["source_url"],
            "builtin": False,
        }
        for row in rows
    ]
