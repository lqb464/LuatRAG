import io
import zipfile

import pytest
from pypdf import PdfWriter

from backend.core.security import ServiceError, clean_filename
from src.rag.documents import extract_document, safe_office_zip


def office_bytes(name, xml):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, xml)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("extension", "part", "xml"),
    [
        (
            "docx",
            "word/document.xml",
            '<w:document xmlns:w="urn:word"><w:body><w:p><w:r><w:t>Quy chế chi phí yêu cầu phê duyệt bằng văn bản.</w:t></w:r></w:p></w:body></w:document>',
        ),
        (
            "pptx",
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="urn:slide" xmlns:a="urn:text"><a:p><a:r><a:t>Quy chế chi phí yêu cầu phê duyệt bằng văn bản.</a:t></a:r></a:p></p:sld>',
        ),
        (
            "xlsx",
            "xl/worksheets/sheet1.xml",
            '<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Quy chế chi phí yêu cầu phê duyệt bằng văn bản.</t></is></c></row></sheetData></worksheet>',
        ),
    ],
)
def test_server_side_openxml_parsing(extension, part, xml):
    segments, parser = extract_document(f"policy.{extension}", office_bytes(part, xml))
    assert "phê duyệt" in segments[0]["text"]
    assert parser == f"{extension}-openxml"


def test_zip_bomb_and_invalid_signature():
    with pytest.raises(ServiceError) as error:
        safe_office_zip(office_bytes("word/document.xml", "a" * 1_000_000))
    assert error.value.status == 413
    with pytest.raises(ServiceError):
        extract_document("fake.pdf", b"A fake PDF document with enough characters")


def test_xml_entities_are_not_expanded():
    xml = (
        '<!DOCTYPE x [<!ENTITY attack "Injected text">]><document><p><t>&attack;</t></p></document>'
    )
    with pytest.raises(ServiceError):
        extract_document("attack.docx", office_bytes("word/document.xml", xml))


def test_scan_pdf_requires_ocr():
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)
    with pytest.raises(ServiceError) as error:
        extract_document("scan.pdf", stream.getvalue())
    assert error.value.code == "ocr_required"


def test_filename_cannot_inject_a_path():
    name = clean_filename("../../hợp đồng:<2026>?.pdf")
    assert not any(char in name for char in "\\/:<>?*")
    assert name.endswith(".pdf")
