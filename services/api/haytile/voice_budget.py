"""Atomic budget changes, independent of HTTP app initialization."""

from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select

from .db import Project, now

INTERNAL_KINDS = ("voice_session", "chat_cleanup")


def fail(code, status=409):
    raise HTTPException(status, detail=code)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reserve(db, user_id, params, credits, prompt):
    sid = params.get("voice_session_id")
    if not sid:
        return
    row = db.scalar(
        select(Project).where(Project.id == sid, Project.user_id == user_id).with_for_update()
    )
    if not row or row.document.get("kind") != "voice_session":
        fail("VOICE_SESSION_ENDED", 409)
    doc = row.document
    from datetime import datetime

    if not doc["active"] or aware(datetime.fromisoformat(doc["expires_at"])) <= now():
        fail("VOICE_SESSION_ENDED", 409)
    if (
        params.get("conversation_id") != doc["conversation_id"]
        or params.get("voice_name") != doc["voice_name"]
        or params.get("session_model_id") != doc["model_id"]
    ):
        fail("VOICE_SESSION_SETTINGS_CHANGED", 409)
    if len(prompt) > doc["max_reply_chars"] or credits > doc["per_reply"]:
        fail("VOICE_REPLY_TOO_LONG", 409)
    if credits > doc["remaining"]:
        fail("VOICE_SESSION_BUDGET_REACHED", 409)
    row.document = {**doc, "remaining": doc["remaining"] - credits}
    row.version += 1


def release(db, job):
    sid = job.params.get("input_params", {}).get("voice_session_id")
    if not sid or not job.credits:
        return
    row = db.scalar(
        select(Project).where(Project.id == sid, Project.user_id == job.user_id).with_for_update()
    )
    if row and row.document.get("kind") == "voice_session":
        row.document = {
            **row.document,
            "remaining": min(row.document["credit_cap"], row.document["remaining"] + job.credits),
        }
        row.version += 1
