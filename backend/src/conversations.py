from uuid import uuid4

from backend.core.security import ServiceError
from backend.src.store import encode_json, now_iso


def validate_conversation(db, owner_id: str, conversation_id: str):
    if not db.execute(
        "SELECT 1 FROM conversations WHERE id = ? AND owner_id = ?", (conversation_id, owner_id)
    ).fetchone():
        raise ServiceError(404, "conversation_not_found", "Không tìm thấy cuộc trao đổi.")


def list_conversations(store, owner_id: str) -> list[dict]:
    with store.connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE owner_id = ? ORDER BY updated_at DESC LIMIT 30",
                (owner_id,),
            )
        ]


def get_conversation(store, owner_id: str, conversation_id: str) -> dict:
    with store.connect() as db:
        validate_conversation(db, owner_id, conversation_id)
        conversation = dict(
            db.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ? AND owner_id = ?",
                (conversation_id, owner_id),
            ).fetchone()
        )
        messages = [
            dict(row)
            for row in db.execute(
                "SELECT id, role, content, evidence_json, created_at FROM messages WHERE conversation_id = ? AND owner_id = ? ORDER BY created_at, rowid LIMIT 100",
                (conversation_id, owner_id),
            )
        ]
    return {"conversation": conversation, "messages": messages}


def delete_conversation(store, owner_id: str, conversation_id: str):
    with store.connect(write=True) as db:
        validate_conversation(db, owner_id, conversation_id)
        db.execute(
            "DELETE FROM conversations WHERE id = ? AND owner_id = ?", (conversation_id, owner_id)
        )


def save_exchange(
    db, owner_id: str, question: str, answer: dict, conversation_id: str | None
) -> str:
    now = now_iso()
    if conversation_id:
        validate_conversation(db, owner_id, conversation_id)
    else:
        conversation_id = str(uuid4())
        db.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
            (conversation_id, owner_id, question[:120], now, now),
        )
    db.execute(
        "INSERT INTO messages VALUES (?, ?, ?, 'user', ?, NULL, ?)",
        (str(uuid4()), conversation_id, owner_id, question, now),
    )
    payload = {
        field: answer[field]
        for field in (
            "summary",
            "answer",
            "claims",
            "limitations",
            "suggestedQuestions",
            "insufficientContext",
            "model",
            "durationMs",
        )
    }
    db.execute(
        "INSERT INTO messages VALUES (?, ?, ?, 'assistant', ?, ?, ?)",
        (
            answer["id"],
            conversation_id,
            owner_id,
            encode_json(payload),
            encode_json(answer["evidence"]),
            now,
        ),
    )
    db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ? AND owner_id = ?",
        (now, conversation_id, owner_id),
    )
    return conversation_id
