import hashlib
import time
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from backend.core.security import ServiceError
from backend.src.conversations import save_exchange, validate_conversation
from backend.src.store import now_iso
from src.rag.core import has_sufficient_evidence


def enforce_rate_limit(store, owner_id: str, action: str):
    now = int(time.time() * 1000)
    window_ms, maximum = (60_000, 20) if action == "ask" else (600_000, 12)
    bucket = now // window_ms
    key = f"{action}:{owner_id}:{bucket}"
    with store.connect(write=True) as db:
        if bucket % 16 == 0:
            db.execute("DELETE FROM rate_limits WHERE expires_at < ?", (now,))
        db.execute(
            "INSERT INTO rate_limits VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET count = count + 1",
            (key, (bucket + 1) * window_ms),
        )
        count = db.execute("SELECT count FROM rate_limits WHERE key = ?", (key,)).fetchone()[
            "count"
        ]
    if count > maximum:
        raise ServiceError(
            429, "rate_limited", "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau."
        )


def prepare_evidence(
    store, corpus, owner_id: str, question: str, conversation_id: str | None, mode: str
):
    enforce_rate_limit(store, owner_id, "ask")
    if conversation_id:
        with store.connect() as db:
            validate_conversation(db, owner_id, conversation_id)
    return corpus.retrieve(store, owner_id, question, 10 if mode == "deep" else 6)


async def ask(
    app, owner_id: str, question: str, conversation_id: str | None = None, mode="fast"
) -> dict:
    started = time.monotonic()
    store, corpus = app.state.store, app.state.corpus
    evidence = await run_in_threadpool(
        prepare_evidence, store, corpus, owner_id, question, conversation_id, mode
    )
    if not has_sufficient_evidence(question, evidence):
        generated = {
            "summary": "Chưa đủ căn cứ trong kho dữ liệu hiện có",
            "answer": "LuatRAG không tìm thấy đoạn văn bản đủ gần để tạo câu trả lời có thể kiểm chứng. Hãy bổ sung tài liệu hoặc hỏi rõ số hiệu, điều khoản.",
            "claims": [],
            "limitations": ["Không gọi Gemini khi bằng chứng truy hồi chưa đạt ngưỡng."],
            "suggestedQuestions": [
                "Điều 113 Bộ luật Lao động 45/2019/QH14 quy định nghỉ hằng năm ra sao?",
                "Nghị định 13/2023/NĐ-CP quy định quyền của chủ thể dữ liệu như thế nào?",
            ],
            "insufficientContext": True,
            "model": "not-called",
        }
    else:
        generated = await app.state.generator(question=question, evidence=evidence)
    answer = {
        **generated,
        "id": str(uuid4()),
        "question": question,
        "durationMs": int((time.monotonic() - started) * 1000),
        "evidence": evidence,
    }
    answer["limitations"] = [
        *generated["limitations"],
        f"Kho mặc định là snapshot {corpus.manifest['snapshotDate']}; cần kiểm tra hiệu lực tại nguồn chính thức.",
    ][:4]

    def persist():
        with store.connect(write=True) as db:
            answer["conversationId"] = save_exchange(
                db, owner_id, question, answer, conversation_id
            )
            db.execute(
                """INSERT INTO query_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()),
                    owner_id,
                    answer["conversationId"],
                    hashlib.sha256(question.encode()).hexdigest(),
                    answer["model"],
                    len(evidence),
                    len(
                        {
                            source_id
                            for claim in answer["claims"]
                            for source_id in claim["sourceIds"]
                        }
                    ),
                    int(answer["insufficientContext"]),
                    answer["durationMs"],
                    now_iso(),
                ),
            )

    await run_in_threadpool(persist)
    return answer
