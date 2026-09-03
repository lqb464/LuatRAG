import math
import re
import unicodedata
from collections import Counter

STOP_WORDS = set(
    "a ai anh ban bang bi bo boi cac cai can cho co cua cung da dang day de den dieu do duoc gi khi khong la lai lam len ma mot nay nen nhu nhung o qua ra rang sau se tai theo thi tren trong tu va ve voi".split()
)
EVIDENCE_STOP_WORDS = set(
    "bao nhieu hien nay sao quy dinh phap luat van ban dieu khoan muc chuong truong hop noi dung ap dung doi tuong ty le dinh thong tu bo luat cau hoi tra loi thong tin nguoi".split()
)
DOCUMENT_NUMBER = re.compile(r"\b\d{1,4}/\d{4}/[a-z0-9-]+\b", re.I)
ARTICLE = re.compile(r"\bdieu\s+(\d+[a-z]?)\b")
HEADING = re.compile(
    r"^(chương\s+[ivxlcdm\d]+|mục\s+\d+|điều\s+\d+[a-z]?|khoản\s+\d+|phần\s+(?:thứ\s+)?[^\W_]+)\s*[.:]?",
    re.I,
)


def normalize_vietnamese(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\0", "")
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[\t\f\v]+", " ", value)
    value = re.sub(r" {2,}", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def fold_vietnamese(value: str) -> str:
    value = unicodedata.normalize("NFD", normalize_vietnamese(value))
    value = re.sub(r"[\u0300-\u036f]", "", value)
    return value.replace("đ", "d").replace("Đ", "D").lower()


def raw_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.sub(r"[^a-z0-9/.-]+", " ", fold_vietnamese(value)).split()
        if len(token) > 1
    ]


def query_tokens(value: str, limit=24) -> list[str]:
    return list(dict.fromkeys(token for token in raw_tokens(value) if token not in STOP_WORDS))[
        :limit
    ]


def build_fts_query(value: str) -> str | None:
    terms = [re.sub(r'["*:^(){}\[\]]', "", term) for term in query_tokens(value, 12)]
    return " OR ".join(f'"{term}"' for term in terms if term) or None


def stable_id(value: str) -> str:
    """Keep the FNV-1a UTF-16 IDs used by existing corpus and local uploads."""
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    hashed = 2166136261
    for index in range(0, len(encoded), 2):
        hashed = (
            (hashed ^ int.from_bytes(encoded[index : index + 2], "little")) * 16777619
        ) & 0xFFFFFFFF
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while hashed:
        hashed, remainder = divmod(hashed, 36)
        result = alphabet[remainder] + result
    return result or "0"


def split_long_paragraph(paragraph: str, max_size: int) -> list[str]:
    if len(paragraph) <= max_size:
        return [paragraph]
    pieces = []
    buffer = ""
    for sentence in re.split(r"(?<=[.!?;])\s+", paragraph):
        if len(sentence) > max_size:
            if buffer:
                pieces.append(buffer.strip())
                buffer = ""
            remaining = sentence.strip()
            while len(remaining) > max_size:
                boundary = remaining.rfind(" ", 0, max_size + 1)
                if boundary < max_size * 0.65:
                    boundary = max_size
                pieces.append(remaining[:boundary].strip())
                remaining = remaining[boundary:].lstrip()
            if remaining:
                pieces.append(remaining)
        else:
            if buffer and len(buffer) + len(sentence) + 1 > max_size:
                pieces.append(buffer.strip())
                buffer = ""
            buffer += (" " if buffer else "") + sentence
    if buffer.strip():
        pieces.append(buffer.strip())
    return pieces


def chunk_segments(
    source_id: str, segments: list[dict], target_size=950, max_size=1400
) -> list[dict]:
    chunks = []
    for segment in segments:
        text = re.sub(
            r"(?<=[.;!?])\s+(?=(?:chương\s+[ivxlcdm\d]+|mục\s+\d+|điều\s+\d+[a-z]?)\s*[.:]?)",
            "\n\n",
            normalize_vietnamese(segment["text"]),
            flags=re.I,
        )
        paragraphs = [
            part.strip()
            for part in re.split(
                r"\n{2,}|(?=^(?:Chương|Mục|Điều|Khoản)\s+)", text, flags=re.I | re.M
            )
            if part.strip()
        ]
        buffer = ""
        heading = (segment.get("heading") or "").strip()

        def flush(active_heading, active_segment=segment):
            nonlocal buffer
            body = normalize_vietnamese(buffer)
            buffer = ""
            if len(body) <= 20:
                return
            ordinal = len(chunks)
            checksum = stable_id(f"{source_id}:{active_segment['locator']}:{body}")
            locator = active_segment.get("locator") or f"Đoạn {ordinal + 1}"
            if active_heading:
                locator = (
                    f"{locator} · {active_heading}"
                    if locator and locator != "Toàn văn"
                    else active_heading
                )
            chunks.append(
                {
                    "id": f"{source_id}:{ordinal}:{checksum}",
                    "ordinal": ordinal,
                    "locator": locator[:240],
                    "heading": active_heading or None,
                    "text": body,
                    "textFolded": fold_vietnamese(body),
                    "checksum": checksum,
                }
            )

        for paragraph in paragraphs:
            marker = HEADING.match(paragraph)
            if marker:
                if buffer:
                    flush(heading)
                title = re.split(
                    r"(?<=[.!?])\s+|\n", paragraph[marker.end() :].strip(), maxsplit=1
                )[0][:150].strip()
                heading = (marker.group().strip() + (f" {title}" if title else ""))[:180]
            for piece in split_long_paragraph(paragraph, max_size):
                if buffer and len(buffer) + len(piece) + 2 > max_size:
                    flush(heading)
                buffer += ("\n\n" if buffer else "") + piece
                if len(buffer) >= target_size:
                    flush(heading)
        flush(heading)
    return chunks


def rank_chunks(question: str, candidates: list[dict], limit=8) -> list[dict]:
    terms = query_tokens(question)
    if not terms or not candidates:
        return []
    doc_terms = [
        Counter(
            token
            for token in raw_tokens(f"{chunk.get('heading') or ''} {chunk['text']}")
            if token not in STOP_WORDS
        )
        for chunk in candidates
    ]
    lengths = [sum(counts.values()) for counts in doc_terms]
    average_length = max(1, sum(lengths) / len(lengths))
    frequency = {term: sum(term in counts for counts in doc_terms) for term in terms}
    folded = fold_vietnamese(question)
    article, number = ARTICLE.search(folded), DOCUMENT_NUMBER.search(folded)
    ranked = []
    for index, chunk in enumerate(candidates):
        title = fold_vietnamese(f"{chunk['sourceName']} {chunk.get('heading') or ''}")
        body = fold_vietnamese(chunk["text"])
        score = 0.0
        for term in terms:
            tf, df = doc_terms[index][term], frequency[term]
            idf = math.log(1 + (len(candidates) - df + 0.5) / (df + 0.5))
            denominator = tf + 1.2 * (0.25 + 0.75 * lengths[index] / average_length)
            score += idf * tf * 2.2 / max(0.1, denominator)
            if term in title:
                score += 0.8
        if article and re.search(rf"dieu\s+{article[1]}\b", body):
            score += 4
        if number and number[0] in fold_vietnamese(chunk.get("documentNumber") or ""):
            score += 7
        if len(folded) > 12 and folded in body:
            score += 3
        status = fold_vietnamese(chunk.get("effectiveStatus") or "")
        if "het hieu luc toan bo" in status:
            score -= 1.2
        elif "het hieu luc mot phan" in status:
            score -= 0.2
        elif "con hieu luc" in status:
            score += 0.45
        score += min(1.5, chunk.get("score") or 0)
        if score > 0.15:
            ranked.append({**chunk, "score": round(score, 4)})
    return sorted(ranked, key=lambda chunk: -chunk["score"])[:limit]


def diversify_chunks(chunks: list[dict], limit=8) -> list[dict]:
    counts = Counter()
    selected = []
    for chunk in chunks:
        if counts[chunk["sourceId"]] >= 3:
            continue
        selected.append(chunk)
        counts[chunk["sourceId"]] += 1
        if len(selected) == limit:
            break
    return selected


def has_sufficient_evidence(question: str, chunks: list[dict]) -> bool:
    if not chunks:
        return False
    folded = fold_vietnamese(question)
    article, number = ARTICLE.search(folded), DOCUMENT_NUMBER.search(folded)

    def article_matches(chunk):
        return not article or bool(
            re.search(
                rf"\bdieu\s+{article[1]}\b",
                fold_vietnamese(f"{chunk['locator']} {chunk.get('heading') or ''} {chunk['text']}"),
            )
        )

    if number:
        matching = [
            chunk
            for chunk in chunks[:8]
            if number[0]
            in fold_vietnamese(f"{chunk.get('documentNumber') or ''} {chunk['sourceName']}")
        ]
        return any(article_matches(chunk) for chunk in matching)
    evidence_question = re.sub(
        r"\b(?:doanh nghiep|cong ty|to chuc|ca nhan|viet nam)\b", " ", folded
    )
    terms = [
        term
        for term in query_tokens(evidence_question, 20)
        if term not in EVIDENCE_STOP_WORDS
        and not re.fullmatch(r"(?:19|20)\d{2}", term)
        and len(term) > 2
    ]
    if len(terms) < 2:
        return False
    matched = set()
    strongest = 0
    for chunk in chunks[:5]:
        tokens = set(
            raw_tokens(
                f"{chunk['sourceName']} {chunk.get('heading') or ''} {chunk['locator']} {chunk['text']}"
            )
        )
        hits = set(terms) & tokens
        matched |= hits
        strongest = max(strongest, len(hits))
    return (
        any(article_matches(chunk) for chunk in chunks[:5])
        and len(matched) >= max(2, math.ceil(len(terms) * 0.8))
        and strongest >= max(2, math.ceil(len(terms) * 0.6))
    )
