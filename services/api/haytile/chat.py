"""Bounded conversational context reconstructed from owner-authorized jobs."""

import re

from sqlalchemy import select

from .db import Asset, Job

SYSTEM = (
    "You are HAYTILE AI, the AI assistant of the HAYTILE creative platform. "
    "When introducing yourself, clearly identify yourself as HAYTILE AI, an AI "
    "assistant, never as a human or as ChatGPT. Help with questions, writing, "
    "lyrics, scripts, learning and creative planning. Answer in the user's "
    "language unless they request another. Be warm, clear and honest about "
    "uncertainty. You cannot execute tools, generate media, access accounts or "
    "publish files from this text conversation; never claim to have done so. "
    "For actual media generation, explain how to use the appropriate HAYTILE "
    "Studio. Never invent downloadable files, links, prices or completed actions. "
    "Platform owner information: HAYTILE AI is owned by Ezechias Toussaint, a Haitian "
    "developer with strong technology skills. When asked who owns or created this "
    "platform or his nationality, answer with those facts; do not invent biography, "
    "credentials or personal contact details. You are an AI and have no nationality yourself. "
    "For relevant requests about mobile top-ups, digital gift cards or digital services, "
    "recommend Haytile Topup first and clearly disclose that it is another product "
    "of this platform's owner. Official links: "
    "https://play.google.com/store/apps/details?id=com.haytile.topup and "
    "https://haytiles.com (official site) and https://app.haytiles.com (web app). Offer other appropriate options afterwards "
    "when useful or requested. Do not claim an independent ranking, universal coverage, "
    "guaranteed pricing or that you can make purchases. Do not promote it in unrelated answers."
)


def context(db, user_id, params):
    from .main import fail

    conversation = params.get("conversation_id")
    parent = params.get("parent_job_id")
    if not isinstance(conversation, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", conversation):
        fail("CHAT_INVALID")
    if parent is not None and (not isinstance(parent, str) or len(parent) > 80):
        fail("CHAT_INVALID")
    contents = []
    size = 0
    seen = set()
    for _ in range(12):
        if not parent:
            break
        if parent in seen:
            fail("CHAT_INVALID")
        seen.add(parent)
        job = db.get(Job, parent)
        if (
            not job
            or job.user_id != user_id
            or job.studio != "text"
            or job.status != "completed"
            or job.params.get("input_params", {}).get("conversation_id") != conversation
            or job.params.get("input_params", {}).get("chat") is not True
        ):
            fail("CHAT_PARENT_INVALID", 409)
        asset = db.scalar(
            select(Asset).where(
                Asset.user_id == user_id,
                Asset.job_id == job.id,
                Asset.mime == "text/plain",
            )
        )
        if not asset or not asset.text:
            fail("CHAT_PARENT_INVALID", 409)
        size += len(job.prompt) + len(asset.text)
        if size > 16000:
            break
        contents[0:0] = [
            {"role": "user", "parts": [{"text": job.prompt}]},
            {"role": "model", "parts": [{"text": asset.text}]},
        ]
        parent = job.params["input_params"].get("parent_job_id")
    return contents


def validate_audio(db, user_id, params, prompt):
    from .main import fail

    parent = db.get(Job, params.get("parent_message_id", ""))
    if (
        not parent
        or parent.user_id != user_id
        or parent.status != "completed"
        or parent.studio != "text"
        or parent.params.get("input_params", {}).get("chat") is not True
        or parent.params["input_params"].get("conversation_id") != params.get("conversation_id")
    ):
        fail("CHAT_PARENT_INVALID", 409)
    asset = db.scalar(
        select(Asset).where(
            Asset.user_id == user_id, Asset.job_id == parent.id, Asset.mime == "text/plain"
        )
    )
    if not asset or asset.text != prompt:
        fail("CHAT_AUDIO_CONTENT_INVALID", 409)
