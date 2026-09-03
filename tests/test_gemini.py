import asyncio
import json

import httpx
import pytest

from src.rag.gemini import GeminiError, generate_legal_answer, validate_generated_payload

VALID = {
    "claims": [{"text": "Thời hạn nộp thuế được gia hạn.", "sourceIds": ["S1"]}],
    "limitations": ["Cần kiểm tra hiệu lực."],
    "suggestedQuestions": [],
    "insufficientContext": False,
}


def test_claim_only_grounded_output():
    parsed = validate_generated_payload(VALID, {"S1", "S2"})
    assert len(parsed["claims"]) == 1
    assert parsed["summary"].startswith("Thời hạn")
    assert "1 nhận định có căn cứ" in parsed["answer"]


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID, "answer": "Uncited text"},
        {**VALID, "insufficientContext": True},
        {**VALID, "claims": []},
        {**VALID, "claims": [{"text": "Invented", "sourceIds": ["S999"]}]},
        {**VALID, "claims": [{"text": "Repeated", "sourceIds": ["S1", "S1"]}]},
        {**VALID, "claims": [{"text": "   ", "sourceIds": ["S1"]}]},
        {**VALID, "insufficientContext": "false"},
    ],
)
def test_fail_closed_generation_contract(payload):
    with pytest.raises(GeminiError):
        validate_generated_payload(payload, {"S1"})


def test_refusal_has_no_claims():
    assert validate_generated_payload(
        {"claims": [], "limitations": [], "suggestedQuestions": [], "insufficientContext": True},
        {"S1"},
    )["insufficientContext"]


def test_gemini_http_contract_and_alias_mapping():
    def handle(request):
        body = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "unit-test-key"
        assert "tools" not in body
        assert body["generationConfig"]["responseJsonSchema"]["properties"]["claims"]["items"][
            "properties"
        ]["sourceIds"]["items"]["enum"] == ["S1"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(VALID)}]}}
                ],
                "modelVersion": "test-model",
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await generate_legal_answer(
                api_key="unit-test-key",
                question="Thuế?",
                evidence=[
                    {
                        "id": "actual-chunk-id",
                        "sourceName": "Luật",
                        "locator": "Điều 1",
                        "text": "Evidence",
                    }
                ],
                client=client,
            )

    result = asyncio.run(run())
    assert result["claims"][0]["sourceIds"] == ["actual-chunk-id"]
    assert result["model"] == "test-model"
