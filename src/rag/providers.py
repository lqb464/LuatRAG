import os
from typing import Protocol

import httpx

from .models import SearchResult


class LLMProvider(Protocol):
    name: str

    def answer(self, question: str, sources: list[SearchResult]) -> str: ...


def prompt_for(question: str, sources: list[SearchResult]) -> str:
    evidence = "\n\n".join(
        f"[{i}] {s.chunk.document_name} — {s.chunk.locator}\n{s.chunk.text}"
        for i, s in enumerate(sources, 1)
    )
    return f"Bạn là trợ lý hỏi đáp dựa trên tài liệu. Chỉ dùng bằng chứng dưới đây. Nếu không đủ căn cứ, hãy nói rõ. Trả lời bằng tiếng Việt và gắn [1], [2]... vào các ý tương ứng.\n\nCÂU HỎI: {question}\n\nBẰNG CHỨNG:\n{evidence}"


class ExtractiveProvider:
    name = "extractive"

    def answer(self, question: str, sources: list[SearchResult]) -> str:
        if not sources:
            return "Chưa tìm thấy đoạn tài liệu phù hợp để trả lời câu hỏi."
        lines = ["Dưới đây là các đoạn liên quan trực tiếp trong kho tài liệu:"]
        for i, source in enumerate(sources, 1):
            snippet = " ".join(source.chunk.text.split())
            if len(snippet) > 420:
                snippet = snippet[:417].rsplit(" ", 1)[0] + "…"
            lines.append(f"\n[{i}] {snippet}")
        return "".join(lines)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def answer(self, question: str, sources: list[SearchResult]) -> str:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt_for(question, sources)}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
        }
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json=body,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model, self.base_url = model, base_url.rstrip("/")

    def answer(self, question: str, sources: list[SearchResult]) -> str:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt_for(question, sources)}],
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


def create_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "extractive").lower()
    if provider == "gemini" and os.getenv("LLM_API_KEY"):
        return GeminiProvider(
            os.environ["LLM_API_KEY"],
            os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        )
    if provider == "ollama":
        return OllamaProvider(
            os.getenv("LLM_MODEL", "qwen2.5:7b"),
            os.getenv("LLM_BASE_URL", "http://localhost:11434"),
        )
    return ExtractiveProvider()
