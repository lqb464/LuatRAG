import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from scripts.fetch_legal_corpus import html_to_text
from src.rag.documents import extract_document


def test_text_layer_pdf_is_parsed_in_python():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 12 Tf 20 700 Td (Written approval is required for every expense above the policy threshold.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    stream = io.BytesIO()
    writer.write(stream)
    segments, parser = extract_document("policy.pdf", stream.getvalue())
    assert parser == "pypdf-text-layer"
    assert segments[0]["locator"] == "Trang 1"
    assert "Written approval" in segments[0]["text"]


@pytest.mark.parametrize("extension", ["txt", "md", "csv"])
def test_utf8_formats_are_parsed_on_server(extension):
    segments, parser = extract_document(
        f"policy.{extension}", "Chính sách thanh toán cần phê duyệt bằng văn bản.".encode()
    )
    assert parser == f"{extension}-utf8"
    assert "phê duyệt" in segments[0]["text"]


def test_public_html_builder_removes_scripts_and_preserves_articles():
    text = html_to_text(
        "<head>ignore me</head><script>ignore me too</script><p>Điều 1. Phạm vi</p><p>Quyền &amp; nghĩa vụ.</p>"
    )
    assert "ignore" not in text
    assert "Điều 1. Phạm vi" in text
    assert "Quyền & nghĩa vụ." in text
