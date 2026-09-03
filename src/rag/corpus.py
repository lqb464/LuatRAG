import json
import re
from pathlib import Path

from src.rag.core import (
    ARTICLE,
    DOCUMENT_NUMBER,
    build_fts_query,
    diversify_chunks,
    fold_vietnamese,
    query_tokens,
    rank_chunks,
)


def searchable(value: str) -> str:
    return " " + " ".join(re.sub(r"[^a-z0-9/.-]+", " ", fold_vietnamese(value)).split()) + " "


class Corpus:
    def __init__(self, path: Path):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        self.manifest = artifact["manifest"]
        self.sources = artifact["documents"]
        sources = {source["id"]: source for source in self.sources}
        self.chunks = []
        for chunk in artifact["chunks"]:
            source = sources[chunk["sourceId"]]
            metadata = {
                field: source.get(field)
                for field in (
                    "sourceUrl",
                    "legalType",
                    "documentNumber",
                    "issuingAuthority",
                    "issueDate",
                    "effectiveStatus",
                )
            }
            self.chunks.append({**chunk, **metadata, "sourceName": source["name"], "builtin": True})
        self.search_text = [
            searchable(
                f"{chunk['sourceName']} {chunk['locator']} {chunk.get('heading') or ''} {chunk['text']}"
            )
            for chunk in self.chunks
        ]
        self.title_text = [
            searchable(f"{chunk['sourceName']} {chunk.get('heading') or ''}")
            for chunk in self.chunks
        ]
        self.document_text = [
            searchable(f"{chunk.get('documentNumber') or ''} {chunk['sourceName']}")
            for chunk in self.chunks
        ]

    def prefilter(self, question: str, limit=192) -> list[dict]:
        terms = query_tokens(question)
        if not terms:
            return []
        folded = searchable(question).strip()
        article, number = ARTICLE.search(folded), DOCUMENT_NUMBER.search(folded)
        scored = []
        for index, chunk in enumerate(self.chunks):
            body, title = self.search_text[index], self.title_text[index]
            score = sum(3 if f" {term} " in title else int(f" {term} " in body) for term in terms)
            if number and f" {number[0]} " in self.document_text[index]:
                score += 18
            if article and f" dieu {article[1]} " in body:
                score += 8
            if len(folded) > 12 and f" {folded} " in body:
                score += 5
            if score:
                scored.append((score, chunk))
        return [chunk for _, chunk in sorted(scored, key=lambda entry: -entry[0])[: max(24, limit)]]

    def retrieve(self, store, owner_id: str, question: str, limit=8) -> list[dict]:
        limit = min(10, max(4, limit))
        static = self.prefilter(question)
        fts = build_fts_query(question)
        custom = []
        if fts:
            with store.connect() as db:
                rows = db.execute(
                    """SELECT c.id, c.source_id, s.name AS source_name, s.source_url,
                       c.locator, c.heading, c.text, -bm25(chunks_fts) AS fts_score
                    FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.chunk_id
                    JOIN sources s ON s.id = c.source_id
                    WHERE chunks_fts MATCH ? AND c.owner_id = ? AND s.status = 'ready'
                    ORDER BY bm25(chunks_fts) LIMIT 30""",
                    (fts, owner_id),
                ).fetchall()
            custom = [
                {
                    "id": row["id"],
                    "sourceId": row["source_id"],
                    "sourceName": row["source_name"],
                    "sourceUrl": row["source_url"],
                    "locator": row["locator"],
                    "heading": row["heading"],
                    "text": row["text"],
                    "score": max(0, min(1.5, row["fts_score"] or 0)),
                    "builtin": False,
                }
                for row in rows
            ]
        return diversify_chunks(rank_chunks(question, [*static, *custom], limit * 2), limit)
