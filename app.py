import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
from src.rag.pipeline import RagPipeline

ROOT = Path(__file__).parent
INDEX_PATH = Path(os.getenv("RAG_INDEX_PATH", ROOT / "data" / "index" / "store.json"))

st.set_page_config(page_title="Project RAG", page_icon="📚", layout="wide")
st.title("📚 Project RAG")
st.caption("Nạp tài liệu · tìm kiếm · hỏi đáp có căn cứ · kiểm tra nguồn")


@st.cache_resource
def get_pipeline() -> RagPipeline:
    return RagPipeline(INDEX_PATH)


pipeline = get_pipeline()
with st.sidebar:
    st.header("Kho tài liệu")
    uploads = st.file_uploader(
        "Nạp tài liệu",
        type=["txt", "md", "csv", "pdf", "docx", "pptx", "xlsx"],
        accept_multiple_files=True,
    )
    if st.button("Lập chỉ mục", type="primary", disabled=not uploads):
        total = 0
        errors = []
        for upload in uploads or []:
            try:
                total += pipeline.ingest_bytes(upload.name, upload.getvalue())
            except Exception as exc:
                errors.append(f"{upload.name}: {exc}")
        st.success(f"Đã lập chỉ mục {total} đoạn.")
        for error in errors:
            st.error(error)
    st.divider()
    st.write(f"**Provider:** `{pipeline.provider.name}`")
    st.write(f"**Tài liệu:** {len(pipeline.index.documents)}")
    st.write(f"**Đoạn:** {len(pipeline.index.chunks)}")
    with st.expander("Danh sách nguồn"):
        for item in pipeline.index.documents_summary():
            st.write(f"📄 {item['name']} · {item['chunks']} đoạn")

question = st.text_area(
    "Câu hỏi", placeholder="Ví dụ: Điều kiện nào được nêu trong tài liệu để...?", height=100
)
col1, col2 = st.columns([1, 5])
with col1:
    limit = st.slider("Số nguồn", 2, 10, 6)
with col2:
    ask = st.button("Tìm kiếm và trả lời", type="primary", disabled=not question.strip())

if ask:
    with st.spinner("Đang truy hồi nguồn và tổng hợp..."):
        result = pipeline.ask(question.strip(), limit)
    st.subheader("Trả lời")
    st.markdown(result.text)
    st.caption(f"Nguồn tổng hợp: `{result.provider}` · Có căn cứ: `{result.grounded}`")
    st.subheader("Nguồn được truy hồi")
    if not result.sources:
        st.info("Chưa có nguồn phù hợp. Hãy nạp tài liệu hoặc thử câu hỏi cụ thể hơn.")
    for number, source in enumerate(result.sources, 1):
        with st.expander(
            f"[{number}] {source.chunk.document_name} · {source.chunk.locator} · điểm {source.score}"
        ):
            st.write(source.chunk.text)
            st.caption(f"ID đoạn: {source.chunk.id}")
else:
    st.info("Nạp tài liệu ở thanh bên, sau đó nhập câu hỏi để bắt đầu demo.")
