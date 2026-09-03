import json
import math
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .documents import chunk_id, file_id, read_document, split_text
from .models import Chunk, Document, SearchResult

STOP_WORDS = {
    "a",
    "ai",
    "anh",
    "ban",
    "bang",
    "bi",
    "bo",
    "boi",
    "cac",
    "cai",
    "can",
    "cho",
    "co",
    "cua",
    "cung",
    "da",
    "dang",
    "day",
    "de",
    "den",
    "dieu",
    "do",
    "duoc",
    "gi",
    "khi",
    "khong",
    "la",
    "lai",
    "lam",
    "len",
    "ma",
    "mot",
    "nay",
    "nen",
    "nhu",
    "nhung",
    "o",
    "qua",
    "ra",
    "rang",
    "sau",
    "se",
    "tai",
    "theo",
    "thi",
    "tren",
    "trong",
    "tu",
    "va",
    "ve",
    "voi",
}


def tokens(value: str) -> list[str]:
    folded = unicodedata_fold(value)
    return [t for t in re.findall(r"[a-z0-9À-ỹ/.-]+", folded) if len(t) > 1 and t not in STOP_WORDS]


def unicodedata_fold(value: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFD", value.lower())
    return "".join(c for c in value if unicodedata.category(c) != "Mn").replace("đ", "d")


class Index:
    def __init__(self, path: Path):
        self.path = path
        self.documents: dict[str, Document] = {}
        self.chunks: list[Chunk] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.documents = {d["id"]: Document(**d) for d in data.get("documents", [])}
        self.chunks = [Chunk(**c) for c in data.get("chunks", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": [asdict(d) for d in self.documents.values()],
            "chunks": [asdict(c) for c in self.chunks],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_file(self, path: Path) -> int:
        content = read_document(path)
        if not content:
            raise ValueError(f"Không đọc được nội dung từ {path.name}")
        document_id = file_id(path)
        self.documents[document_id] = Document(
            document_id, path.name, str(path), content, {"extension": path.suffix.lower()}
        )
        self.chunks = [c for c in self.chunks if c.document_id != document_id]
        parts = split_text(content)
        self.chunks.extend(
            Chunk(
                chunk_id(document_id, i, part),
                document_id,
                path.name,
                part,
                f"Đoạn {i + 1}",
                self.documents[document_id].metadata,
            )
            for i, part in enumerate(parts)
        )
        self.save()
        return len(parts)

    def add_bytes(self, name: str, value: bytes) -> int:
        target = self.path.parent.parent / "documents" / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        return self.add_file(target)

    def remove_document(self, document_id: str) -> None:
        self.documents.pop(document_id, None)
        self.chunks = [c for c in self.chunks if c.document_id != document_id]
        self.save()

    def search(self, query: str, limit: int = 6) -> list[SearchResult]:
        q = Counter(tokens(query))
        if not q:
            return []
        df = Counter(t for c in self.chunks for t in set(tokens(c.text)))
        scored: list[SearchResult] = []
        for chunk in self.chunks:
            doc = Counter(tokens(f"{chunk.document_name} {chunk.locator} {chunk.text}"))
            score = 0.0
            for term, count in q.items():
                if term in doc:
                    score += (
                        (1 + math.log(count))
                        * (1 + math.log(doc[term]))
                        * math.log(1 + (1 + len(self.chunks)) / (1 + df[term]))
                    )
            if score > 0:
                scored.append(SearchResult(chunk, round(score, 5)))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def documents_summary(self) -> list[dict]:
        return [
            {
                "id": d.id,
                "name": d.name,
                "chunks": sum(c.document_id == d.id for c in self.chunks),
                "metadata": d.metadata,
            }
            for d in self.documents.values()
        ]
