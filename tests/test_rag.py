import pytest

from src.rag.core import (
    build_fts_query,
    chunk_segments,
    fold_vietnamese,
    has_sufficient_evidence,
    normalize_vietnamese,
    rank_chunks,
    stable_id,
)


def chunk(**overrides):
    return {
        "id": "chunk-1",
        "sourceId": "source-1",
        "sourceName": "Bộ luật Lao động số 45/2019/QH14",
        "locator": "Điều 113. Nghỉ hằng năm",
        "heading": "Điều 113. Nghỉ hằng năm",
        "text": "Người lao động làm việc đủ 12 tháng được nghỉ hằng năm và hưởng nguyên lương.",
        "documentNumber": "45/2019/QH14",
        **overrides,
    }


def test_vietnamese_normalization_and_fts():
    assert normalize_vietnamese("  Luật\r\n\r\n\r\n  Việt\tNam  ") == "Luật\n\n Việt Nam"
    assert fold_vietnamese("ĐIỀU 113 – Nghỉ hằng năm") == "dieu 113 – nghi hang nam"
    assert build_fts_query("và của là") is None
    assert build_fts_query('thuế " OR * (tài chính)') == '"thue" OR "or" OR "chinh"'


def test_legal_chunk_boundaries_and_stable_ids():
    text = (
        "Điều 1. Phạm vi áp dụng\n\n"
        + "Quy định pháp luật dành cho người lao động. " * 120
        + "\n\nĐiều 2. Trách nhiệm\n\nNgười sử dụng lao động có trách nhiệm thực hiện đầy đủ nghĩa vụ."
    )
    chunks = chunk_segments("s", [{"locator": "Toàn văn", "text": text}])
    assert len(chunks) >= 4
    assert all(20 < len(entry["text"]) <= 1400 for entry in chunks)
    assert all(entry["locator"].startswith("Điều") for entry in chunks)
    assert chunks == chunk_segments("s", [{"locator": "Toàn văn", "text": text}])
    assert stable_id("hello") == "m3bicr"


def test_exact_document_number_and_effective_status():
    candidates = [
        chunk(id="wrong", documentNumber="01/2020/NĐ-CP", sourceName="Văn bản khác"),
        chunk(id="right"),
    ]
    assert rank_chunks("Điều 113 Bộ luật Lao động 45/2019/QH14", candidates)[0]["id"] == "right"
    candidates = [
        chunk(id="expired", effectiveStatus="Hết hiệu lực toàn bộ"),
        chunk(id="current", effectiveStatus="Còn hiệu lực"),
    ]
    assert rank_chunks("nghỉ hằng năm", candidates)[0]["id"] == "current"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Điều 113 Bộ luật Lao động 45/2019/QH14", True),
        ("Điều 114 Bộ luật Lao động 45/2019/QH14", False),
        ("Điều 113 của văn bản 99/2026/QH15", False),
        ("Quy định khai thác heli trên Sao Hỏa cho doanh nghiệp Việt Nam là gì?", False),
    ],
)
def test_evidence_gate(question, expected):
    assert has_sufficient_evidence(question, [chunk()]) is expected
