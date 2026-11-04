"""Owner-approved, bounded automatic TTS sessions, persisted with creative metadata."""

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import pricing
from .db import Project, Session, User, now
from .main import current, fail, limit
from .model_choices import select_choice
from .trials import lock_sqlite_write
from .voice_choices import VOICES

router = APIRouter()


class StartVoice(BaseModel):
    conversation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,80}$")
    model_id: str = Field(min_length=1, max_length=120)
    voice_name: str
    credit_cap: int = Field(ge=1, le=5000)
    confirmed_per_reply: int = Field(ge=1, le=100000)


def snapshot(project):
    return {"id": project.id, **project.document}


@router.post("/v1/chat/voice-sessions", status_code=201)
def start(body: StartVoice, user=Depends(current)):
    if body.voice_name not in VOICES:
        fail("VOICE_INVALID")
    limit("voice-session:" + user.id, 20, 3600)
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user.id).with_for_update())
        model = select_choice(db, "voice", body.model_id)
        if not model or not model.enabled:
            fail("MODEL_NOT_APPROVED", 409)
        per_reply = pricing.quote(
            "voice", model.model_id, "a" * 1000, {"voice_name": body.voice_name}, model.credits
        )["credits"]
        if per_reply != body.confirmed_per_reply or per_reply <= 0:
            fail("PRICE_CHANGED", 409)
        if body.credit_cap < per_reply:
            fail("VOICE_BUDGET_TOO_SMALL", 409)
        if owner.balance - owner.reserved < per_reply:
            fail("INSUFFICIENT_CREDITS", 402)
        project = Project(
            user_id=user.id,
            title="Voice conversation",
            document={
                "kind": "voice_session",
                "conversation_id": body.conversation_id,
                "model_id": model.model_id,
                "voice_name": body.voice_name,
                "credit_cap": body.credit_cap,
                "remaining": body.credit_cap,
                "per_reply": per_reply,
                "max_reply_chars": 1000,
                "active": True,
                "expires_at": (now() + timedelta(minutes=30)).isoformat(),
            },
        )
        db.add(project)
        db.flush()
        return snapshot(project)


@router.get("/v1/chat/voice-sessions/{session_id}")
def get(session_id: str, user=Depends(current)):
    with Session() as db:
        row = db.get(Project, session_id)
        if not row or row.user_id != user.id or row.document.get("kind") != "voice_session":
            fail("NOT_FOUND", 404)
        return snapshot(row)


@router.post("/v1/chat/voice-sessions/{session_id}/stop")
def stop(session_id: str, user=Depends(current)):
    with Session.begin() as db:
        row = db.scalar(
            select(Project)
            .where(Project.id == session_id, Project.user_id == user.id)
            .with_for_update()
        )
        if not row or row.document.get("kind") != "voice_session":
            fail("NOT_FOUND", 404)
        row.document = {**row.document, "active": False}
        row.version += 1
    return {"ok": True}
