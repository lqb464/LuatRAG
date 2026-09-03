# Project RAG

Project này tập trung vào một pipeline RAG Python có thể đọc tài liệu, truy hồi đoạn liên quan, tổng hợp câu trả lời và hiển thị nguồn. Giao diện chỉ là Streamlit demo để kiểm tra nhanh các chức năng RAG.

## Chức năng

- Nạp TXT, Markdown, CSV, PDF có lớp text, DOCX, PPTX và XLSX.
- Tách tài liệu thành các đoạn có mã nguồn và vị trí.
- Tìm kiếm theo xếp hạng từ vựng xác định, không cần dịch vụ vector database.
- Hỏi đáp có trích dẫn dạng `[1]`, `[2]` và mở rộng từng đoạn nguồn trong UI.
- Provider LLM thay được: `extractive` (mặc định, không cần API), `gemini` hoặc `ollama`.
- Chỉ lưu index cục bộ trong `data/index/store.json`; tài liệu upload nằm trong `data/documents`.

## Kiến trúc

```text
Tài liệu -> loader -> chunker -> index cục bộ -> retrieval -> evidence
                                                   |              |
                                                   +-> provider --+-> Answer + sources

app.py (Streamlit) chỉ gọi RagPipeline; không có frontend JavaScript hoặc API backend riêng.
```

`src/rag/providers.py` chứa interface provider chung. Đổi Gemini sang Ollama hoặc provider local bằng biến môi trường, không phải sửa pipeline.

## Chạy local

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
streamlit run app.py
```

Mở URL Streamlit được in trong terminal, thường là `http://localhost:8501`. Nạp file ở sidebar, bấm **Lập chỉ mục**, nhập câu hỏi và bấm **Tìm kiếm và trả lời**.

## Chọn model

Mặc định project dùng câu trả lời trích xuất, phù hợp để demo ngay cả khi không có API:

```dotenv
LLM_PROVIDER=extractive
```

Dùng Gemini qua adapter chung:

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=your-key
LLM_MODEL=gemini-2.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

Dùng model local qua Ollama:

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
LLM_BASE_URL=http://localhost:11434
```

Nếu provider không gọi được, pipeline tự rơi về câu trả lời trích xuất kèm nguồn để demo vẫn hoạt động.

## Nạp dữ liệu mẫu bằng CLI

```bash
python scripts/index_documents.py data/examples
```

Sau đó chạy Streamlit và hỏi về nội dung trong thư mục mẫu. Có thể đặt tài liệu của bạn vào `data/documents` rồi chạy lại lệnh trên.

## Đề xuất công nghệ

Bản hiện tại dùng retrieval từ vựng nhẹ để chạy được ngay trên máy cá nhân và dễ kiểm tra provenance. Khi corpus lớn hơn, có thể thêm một implementation `EmbeddingProvider`/`VectorStore` bên cạnh index hiện tại, giữ nguyên `RagPipeline` và UI. LLM đã được tách qua provider nên chuyển sang model local không ảnh hưởng phần nạp, chunk hay citation.

## Giới hạn demo

- PDF scan cần OCR trước.
- Index JSON phù hợp demo và corpus nhỏ; production nên thay bằng SQLite FTS hoặc vector database.
- Trích dẫn chỉ thể hiện đoạn đã truy hồi, không thay thế việc kiểm tra toàn văn và hiệu lực văn bản.
