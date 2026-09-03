import hashlib
import re
import unicodedata
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx", ".pptx", ".xlsx"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\x00", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[\t\f\v]+", " ", value)
    value = re.sub(r"[ ]{2,}", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def file_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def chunk_id(document_id: str, ordinal: int, text: str) -> str:
    digest = hashlib.sha256(f"{document_id}:{ordinal}:{text}".encode()).hexdigest()[:12]
    return f"{document_id}-{ordinal:04d}-{digest}"


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Định dạng chưa được hỗ trợ: {suffix or '(không có đuôi)'}")
    if suffix in {".txt", ".md", ".csv"}:
        return normalize_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".pdf":
        from pypdf import PdfReader

        return normalize_text(
            "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        )
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

        def xml_text(name: str) -> str:
            root = ET.fromstring(archive.read(name))
            return " ".join(
                (node.text or "")
                for node in root.iter()
                if node.tag.rsplit("}", 1)[-1] in {"t", "v"}
            )

        if suffix == ".docx":
            return normalize_text(xml_text("word/document.xml"))
        if suffix == ".pptx":
            slides = sorted(
                name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            )
            return normalize_text("\n\n".join(xml_text(name) for name in slides))
        sheets = sorted(
            name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        return normalize_text("\n\n".join(xml_text(name) for name in sheets))


def split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = (
            [paragraph[i : i + size] for i in range(0, len(paragraph), size)]
            if len(paragraph) > size
            else [paragraph]
        )
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > size:
                chunks.append(current.strip())
                tail = current[-overlap:] if overlap else ""
                current = f"{tail}\n\n{piece}" if tail else piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks
