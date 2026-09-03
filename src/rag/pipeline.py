from pathlib import Path

from .index import Index
from .models import Answer, SearchResult
from .providers import create_provider


class RagPipeline:
    def __init__(self, index_path: Path):
        self.index = Index(index_path)
        self.provider = create_provider()

    def ingest_file(self, path: Path) -> int:
        return self.index.add_file(path)

    def ingest_bytes(self, name: str, value: bytes) -> int:
        return self.index.add_bytes(name, value)

    def search(self, question: str, limit: int = 6) -> list[SearchResult]:
        return self.index.search(question, limit)

    def ask(self, question: str, limit: int = 6) -> Answer:
        sources = self.search(question, limit)
        try:
            text = self.provider.answer(question, sources)
            provider = self.provider.name
        except Exception:
            text = (
                "Không gọi được model đã cấu hình; hiển thị câu trả lời trích xuất từ nguồn.\n\n"
                + self._extractive(sources)
            )
            provider = "extractive-fallback"
        return Answer(text, sources, provider, bool(sources))

    @staticmethod
    def _extractive(sources: list[SearchResult]) -> str:
        if not sources:
            return "Chưa tìm thấy đoạn tài liệu phù hợp."
        return "\n\n".join(f"[{i}] {s.chunk.text[:420]}" for i, s in enumerate(sources, 1))
