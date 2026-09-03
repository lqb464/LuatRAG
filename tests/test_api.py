import json

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app

POLICY = "QUY CHẾ KIỂM SOÁT CHI PHÍ\n\nĐiều 1. Phê duyệt\n\nKhoản chi trên 10.000.000 đồng cần phê duyệt bằng văn bản của quản lý."


def upload(client, **kwargs):
    response = client.post(
        "/api/sources", files={"file": ("policy.txt", POLICY.encode(), "text/plain")}, **kwargs
    )
    assert response.status_code == 201, response.text
    return response.json()["source"]


def test_health_corpus_and_refusal_without_provider(client):
    assert client.get("/api/health").json()["storage"] == {"sqlite": True, "filesystem": True}
    sources = client.get("/api/sources").json()["sources"]
    assert sum(source.get("builtin", False) for source in sources) >= 24
    response = client.post(
        "/api/ask",
        json={"question": "Quy định khai thác heli trên Sao Hỏa cho doanh nghiệp Việt Nam là gì?"},
    )
    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert answer["model"] == "not-called"
    history = client.get(f"/api/conversations/{answer['conversationId']}").json()
    assert [message["role"] for message in history["messages"]] == ["user", "assistant"]


def test_upload_reindex_tenant_isolation_and_delete(client, app):
    source = upload(
        client,
        data={
            "extraction": json.dumps(
                {
                    "segments": [
                        {
                            "locator": "Fake",
                            "text": "Injected extraction that must never be indexed",
                        }
                    ]
                }
            )
        },
    )
    source_id = source["id"]
    evidence = client.get(f"/api/sources/{source_id}").json()["evidence"]
    assert any("phê duyệt" in chunk["text"] for chunk in evidence)
    assert all("Injected" not in chunk["text"] for chunk in evidence)
    assert (
        client.post(f"/api/sources/{source_id}/reindex").json()["chunkCount"]
        == source["chunkCount"]
    )
    other = {"oai-authenticated-user-id": "other-user"}
    for method, suffix in [("GET", ""), ("DELETE", ""), ("POST", "/reindex")]:
        assert (
            client.request(method, f"/api/sources/{source_id}{suffix}", headers=other).status_code
            == 404
        )
    with app.state.store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ('"phe"',)
            ).fetchone()[0]
            > 0
        )
    assert client.delete(f"/api/sources/{source_id}").status_code == 200
    assert client.get(f"/api/sources/{source_id}").status_code == 404
    assert not list(app.state.store.objects_dir.iterdir())
    with app.state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == 0


def test_grounded_answer_and_source_delete_cascade(client, app):
    source = upload(client)

    async def grounded(**kwargs):
        assert any(chunk["sourceId"] == source["id"] for chunk in kwargs["evidence"])
        relevant = next(chunk for chunk in kwargs["evidence"] if chunk["sourceId"] == source["id"])
        return {
            "summary": "Phê duyệt chi phí",
            "answer": "Một nhận định có căn cứ.",
            "claims": [
                {"text": "Khoản chi cần phê duyệt bằng văn bản.", "sourceIds": [relevant["id"]]}
            ],
            "limitations": [],
            "suggestedQuestions": [],
            "insufficientContext": False,
            "model": "test-model",
        }

    app.state.generator = grounded
    response = client.post(
        "/api/ask",
        json={"question": "Quy chế kiểm soát chi phí quy định phê duyệt bằng văn bản như thế nào?"},
    )
    assert response.status_code == 200, response.text
    conversation_id = response.json()["answer"]["conversationId"]
    assert (
        client.get(
            f"/api/conversations/{conversation_id}", headers={"oai-authenticated-user-id": "other"}
        ).status_code
        == 404
    )
    client.delete(f"/api/sources/{source['id']}")
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    with app.state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_cross_origin_and_streaming_body_limits(client):
    assert (
        client.post(
            "/api/ask",
            json={"question": "Test question"},
            headers={"origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/ask",
            json={"question": "Test question"},
            headers={"origin": "http://localhost:3000"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/ask",
            content=iter([b"x" * 20_000, b"x" * 20_000]),
            headers={"content-type": "application/json"},
        ).status_code
        == 413
    )
    assert client.post("/api/ask", json={"question": "  "}).status_code == 422


def test_production_requires_bff_and_identity(tmp_path):
    secret = "unit-test-server-secret-" * 3
    settings = Settings(
        app_env="production",
        data_dir=tmp_path,
        frontend_origin="https://luatrag.example",
        bff_secret=secret,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 401
        assert (
            client.get("/api/health", headers={"oai-authenticated-user-id": "forged"}).status_code
            == 401
        )
        assert (
            client.get("/api/health", headers={"x-luatrag-bff-secret": secret}).status_code == 401
        )
        assert (
            client.get(
                "/api/health",
                headers={
                    "x-luatrag-bff-secret": secret,
                    "oai-authenticated-user-id": "trusted-user",
                },
            ).status_code
            == 200
        )
        assert client.get("/docs").status_code == 404
