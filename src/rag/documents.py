import io
import re
import zipfile

from defusedxml import ElementTree as ET
from pypdf import PdfReader

from src.errors import ServiceError
from src.rag.core import normalize_vietnamese

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024
EXTENSION_KIND = {
    "pdf": "pdf",
    "docx": "document",
    "pptx": "slides",
    "xlsx": "sheet",
    "txt": "text",
    "md": "text",
    "csv": "sheet",
}


def validated_segments(value) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= 600:
        raise ServiceError(400, "invalid_extraction", "Kết quả trích xuất không hợp lệ.")
    segments = []
    total = 0
    for index, item in enumerate(value):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("text"), str)
            or not isinstance(item.get("locator"), str)
        ):
            raise ServiceError(400, "invalid_extraction", "Thiếu nội dung hoặc vị trí trích xuất.")
        text = normalize_vietnamese(item["text"])
        if len(text) > 120_000:
            raise ServiceError(413, "segment_too_large", "Phần trích xuất vượt quá 120.000 ký tự.")
        total += len(text.encode())
        if text:
            segments.append(
                {
                    "text": text,
                    "locator": normalize_vietnamese(item["locator"])[:180] or f"Đoạn {index + 1}",
                    "heading": normalize_vietnamese(item.get("heading") or "")[:240],
                }
            )
    if total > MAX_EXTRACTED_BYTES:
        raise ServiceError(
            413, "extracted_text_too_large", "Phần văn bản trích xuất vượt quá 2 MB."
        )
    if not any(len(segment["text"]) >= 20 for segment in segments):
        raise ServiceError(
            422, "no_extractable_text", "Không tìm thấy lớp văn bản có thể lập chỉ mục."
        )
    return segments


def safe_office_zip(value: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(value))
        entries = archive.infolist()
    except (zipfile.BadZipFile, ValueError) as error:
        raise ServiceError(
            415, "invalid_file_signature", "Tệp Office không có cấu trúc ZIP hợp lệ."
        ) from error
    total = 0
    if not entries or len(entries) > 5000:
        archive.close()
        raise ServiceError(413, "unsafe_office_zip_bomb", "Gói Office có quá nhiều tệp bên trong.")
    for entry in entries:
        total += entry.file_size
        if entry.flag_bits & 1:
            archive.close()
            raise ServiceError(
                415, "unsafe_office_encrypted", "Tệp Office được mã hóa chưa được hỗ trợ."
            )
        if total > 40 * 1024 * 1024 or (
            entry.file_size and entry.file_size / max(1, entry.compress_size) > 120
        ):
            archive.close()
            raise ServiceError(
                413, "unsafe_office_zip_bomb", "Gói Office vượt giới hạn giải nén an toàn."
            )
    return archive


def xml_text(node) -> str:
    return " ".join(
        element.text or "" for element in node.iter() if element.tag.rsplit("}", 1)[-1] == "t"
    ).strip()


def parse_office(extension: str, value: bytes) -> list[dict]:
    with safe_office_zip(value) as archive:
        names = archive.namelist()
        if extension == "docx":
            if "word/document.xml" not in names:
                raise ServiceError(415, "invalid_office_structure", "DOCX thiếu word/document.xml.")
            document = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = [
                xml_text(node) for node in document.iter() if node.tag.rsplit("}", 1)[-1] == "p"
            ]
            return [
                {"locator": "Toàn văn", "text": "\n\n".join(part for part in paragraphs if part)}
            ]
        if extension == "pptx":
            slides = sorted(
                (name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"slide(\d+)", name)[1]),
            )
            if not slides:
                raise ServiceError(415, "invalid_office_structure", "PPTX thiếu nội dung slide.")
            return [
                {
                    "locator": f"Slide {index + 1}",
                    "text": xml_text(ET.fromstring(archive.read(name))),
                }
                for index, name in enumerate(slides)
            ]
        sheets = sorted(
            (name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)),
            key=lambda name: int(re.search(r"sheet(\d+)", name)[1]),
        )
        if not sheets:
            raise ServiceError(415, "invalid_office_structure", "XLSX thiếu nội dung worksheet.")
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                xml_text(node)
                for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))
                if node.tag.rsplit("}", 1)[-1] == "si"
            ]
        segments = []
        for sheet_index, name in enumerate(sheets):
            document = ET.fromstring(archive.read(name))
            for row in document.iter():
                if row.tag.rsplit("}", 1)[-1] != "row":
                    continue
                cells = []
                for cell in row:
                    kind = cell.get("t")
                    raw = next(
                        (child.text or "" for child in cell if child.tag.rsplit("}", 1)[-1] == "v"),
                        "",
                    )
                    value = xml_text(cell) if kind == "inlineStr" else raw
                    if kind == "s":
                        value = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
                    if value:
                        cells.append(f"{cell.get('r', 'Ô')}: {value}")
                if cells:
                    segments.append(
                        {
                            "locator": f"Sheet {sheet_index + 1} · Hàng {row.get('r', str(len(segments) + 1))}",
                            "text": " | ".join(cells),
                        }
                    )
                if len(segments) > 600:
                    raise ServiceError(
                        413, "too_many_segments", "Tài liệu vượt quá 600 phần trích xuất."
                    )
        return segments


def extract_document(name: str, value: bytes) -> tuple[list[dict], str]:
    extension = name.rsplit(".", 1)[-1].lower()
    if extension not in EXTENSION_KIND:
        raise ServiceError(
            415,
            "unsupported_file_type",
            "Định dạng được hỗ trợ: PDF, DOCX, PPTX, XLSX, TXT, MD và CSV.",
        )
    if not 0 < len(value) <= MAX_FILE_BYTES:
        raise ServiceError(413, "file_too_large", "Tệp phải có kích thước tối đa 10 MB.")
    try:
        if extension == "pdf":
            if not value.startswith(b"%PDF"):
                raise ServiceError(415, "invalid_file_signature", "Tệp không phải PDF hợp lệ.")
            reader = PdfReader(io.BytesIO(value))
            if reader.is_encrypted:
                raise ServiceError(415, "encrypted", "PDF được mã hóa chưa được hỗ trợ.")
            if len(reader.pages) > 300:
                raise ServiceError(413, "too_many_pages", "PDF vượt giới hạn 300 trang.")
            segments = [
                {"locator": f"Trang {index + 1}", "text": page.extract_text() or ""}
                for index, page in enumerate(reader.pages)
            ]
            if sum(len(item["text"]) for item in segments) < 40:
                raise ServiceError(
                    422, "ocr_required", "PDF không có lớp văn bản. Hãy OCR tệp trước khi tải lên."
                )
            parser = "pypdf-text-layer"
        elif extension in {"docx", "pptx", "xlsx"}:
            segments = parse_office(extension, value)
            parser = f"{extension}-openxml"
        else:
            text = value.decode("utf-8-sig").replace("\0", "").strip()
            lines = [line for line in text.splitlines() if line.strip()]
            segments = [
                {
                    "locator": f"Dòng {start + 1}–{min(len(lines), start + 80)}",
                    "text": "\n".join(lines[start : start + 80]),
                }
                for start in range(0, len(lines), 80)
            ]
            parser = f"{extension}-utf8"
    except ServiceError:
        raise
    except Exception as error:
        raise ServiceError(415, "invalid_file", "Không thể đọc nội dung tài liệu.") from error
    return validated_segments(segments), parser
