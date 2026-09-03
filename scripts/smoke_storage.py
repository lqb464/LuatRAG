import argparse

import httpx


def smoke(base_url: str, *, with_gemini=False):
    conversation_ids = []
    source_id = None
    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=60, headers={"origin": base_url.rstrip("/")}
    ) as client:

        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise AssertionError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()

        try:
            health = request("GET", "/api/health")
            assert health["storage"]["sqlite"] and health["storage"]["filesystem"]
            sources = request("GET", "/api/sources")["sources"]
            builtin_count = sum(source.get("builtin", False) for source in sources)
            assert builtin_count >= 24
            refusal = request(
                "POST",
                "/api/ask",
                json={
                    "question": "Quy định khai thác heli trên Sao Hỏa cho doanh nghiệp Việt Nam là gì?"
                },
            )["answer"]
            conversation_ids.append(refusal["conversationId"])
            assert refusal["insufficientContext"] and refusal["model"] == "not-called"
            source = request(
                "POST",
                "/api/sources",
                files={
                    "file": (
                        "quy-che-ci.txt",
                        "QUY CHẾ KIỂM SOÁT CHI PHÍ CI\n\nĐiều 1. Phê duyệt\n\nKhoản chi trên 10.000.000 đồng cần phê duyệt bằng văn bản.".encode(),
                        "text/plain",
                    )
                },
            )["source"]
            source_id = source["id"]
            assert source["status"] == "ready" and source["chunkCount"] >= 1
            assert request("POST", f"/api/sources/{source_id}/reindex")["chunkCount"] >= 1
            assert request("GET", f"/api/sources/{source_id}")["evidence"]
            assert (
                client.get(
                    f"/api/sources/{source_id}",
                    headers={"oai-authenticated-user-id": "smoke-other-user"},
                ).status_code
                == 404
            )
            request("DELETE", f"/api/sources/{source_id}")
            assert client.get(f"/api/sources/{source_id}").status_code == 404
            source_id = None
            gemini_citations = None
            if with_gemini:
                assert health["generation"]["configured"], "Backend Gemini key is not configured"
                answer = request(
                    "POST",
                    "/api/ask",
                    json={
                        "question": "Điều 113 Bộ luật Lao động 45/2019/QH14 quy định nghỉ hằng năm ra sao?",
                        "mode": "fast",
                    },
                )["answer"]
                conversation_ids.append(answer["conversationId"])
                evidence_ids = {chunk["id"] for chunk in answer["evidence"]}
                assert not answer["insufficientContext"] and answer["claims"]
                assert all(
                    source_id in evidence_ids
                    for claim in answer["claims"]
                    for source_id in claim["sourceIds"]
                )
                gemini_citations = sum(len(claim["sourceIds"]) for claim in answer["claims"])
            print(
                {
                    "status": "ok",
                    "builtinSources": builtin_count,
                    "pythonParsing": True,
                    "uploadReindexDelete": True,
                    "refusalSkippedGemini": True,
                    "geminiCitations": gemini_citations,
                }
            )
        finally:
            if source_id:
                request("DELETE", f"/api/sources/{source_id}")
            for conversation_id in conversation_ids:
                request("DELETE", f"/api/conversations/{conversation_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument(
        "--with-gemini",
        action="store_true",
        help="Also verify one public-corpus question using the configured provider key",
    )
    args = parser.parse_args()
    smoke(args.base_url, with_gemini=args.with_gemini)
