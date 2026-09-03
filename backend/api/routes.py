from typing import Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from backend.core.security import User, request_user
from backend.src import conversations, sources
from backend.src.service import ask, enforce_rate_limit
from src.rag.core import normalize_vietnamese
from src.rag.documents import MAX_FILE_BYTES

router = APIRouter(prefix="/api")


class AskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=4, max_length=1200)
    conversationId: str | None = Field(default=None, max_length=99)
    mode: Literal["fast", "deep"] = "fast"

    @field_validator("question", mode="before")
    @classmethod
    def normalize(cls, value):
        return normalize_vietnamese(value) if isinstance(value, str) else value


@router.get("/health")
def health(request: Request, user: User = Depends(request_user)):
    with request.app.state.store.connect() as db:
        db.execute("SELECT 1").fetchone()
    settings = request.app.state.settings
    return {
        "status": "ok",
        "authenticated": True,
        "user": {"email": user.email},
        "storage": {"sqlite": True, "filesystem": request.app.state.store.objects_dir.is_dir()},
        "generation": {"configured": bool(settings.gemini_api_key), "model": settings.gemini_model},
    }


@router.post("/ask")
async def ask_question(body: AskInput, request: Request, user: User = Depends(request_user)):
    return {
        "answer": await ask(request.app, user.id, body.question, body.conversationId, body.mode)
    }


@router.get("/sources")
def list_sources(request: Request, user: User = Depends(request_user)):
    corpus = request.app.state.corpus
    return {
        "sources": sources.list_sources(request.app.state.store, corpus, user.id),
        "corpus": corpus.manifest,
    }


@router.post("/sources", status_code=201)
async def upload_source(
    request: Request, file: UploadFile = File(...), user: User = Depends(request_user)
):
    store = request.app.state.store
    await run_in_threadpool(enforce_rate_limit, store, user.id, "upload")
    try:
        value = await file.read(MAX_FILE_BYTES + 1)
        source = await run_in_threadpool(
            sources.create_source,
            store,
            user.id,
            file.filename or "",
            file.content_type or "",
            value,
        )
    finally:
        await file.close()
    return {"source": source}


@router.get("/sources/{source_id}")
def get_source(source_id: str, request: Request, user: User = Depends(request_user)):
    return {
        "evidence": sources.source_evidence(
            request.app.state.store, request.app.state.corpus, user.id, source_id
        )
    }


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, request: Request, user: User = Depends(request_user)):
    sources.delete_source(request.app.state.store, user.id, source_id)
    return {"deleted": True}


@router.post("/sources/{source_id}/reindex")
def reindex_source(source_id: str, request: Request, user: User = Depends(request_user)):
    return {
        "reindexed": True,
        "chunkCount": sources.reindex_source(request.app.state.store, user.id, source_id),
    }


@router.get("/conversations")
def list_conversations(request: Request, user: User = Depends(request_user)):
    return {"conversations": conversations.list_conversations(request.app.state.store, user.id)}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request, user: User = Depends(request_user)):
    return conversations.get_conversation(request.app.state.store, user.id, conversation_id)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, user: User = Depends(request_user)):
    conversations.delete_conversation(request.app.state.store, user.id, conversation_id)
    return {"deleted": True}
