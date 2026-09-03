from dataclasses import dataclass, field


@dataclass(slots=True)
class Document:
    id: str
    name: str
    path: str
    content: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    id: str
    document_id: str
    document_name: str
    text: str
    locator: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    chunk: Chunk
    score: float


@dataclass(slots=True)
class Answer:
    text: str
    sources: list[SearchResult]
    provider: str
    grounded: bool
