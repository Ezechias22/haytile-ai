"""Native PCM speech-to-speech relay. Never sends audio through text/TTS jobs."""

import asyncio
import base64
import json
import os
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.requests import Request
from websockets.asyncio.client import connect

from . import chat, records, wallets
from .availability import generation_enabled
from .db import Job, Ledger, Session, User, now
from .main import aware, current, fail, limit
from .trials import lock_sqlite_write
from .voice_choices import VOICES

router = APIRouter()
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
# Haytile block price, not a Google per-minute price. See docs/NATIVE_LIVE_VOICE.md.
CREDITS = 70
SECONDS = 60
MAX_USAGE = 8000
ENDPOINT = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


def enabled():
    return (
        os.environ.get("HAYTILE_LIVE_VOICE_ENABLED") == "1"
        and generation_enabled()
        and bool(os.environ.get("HAYTILE_GEMINI_API_KEY"))
    )


@router.get("/v1/chat/live/config")
def config():
    return {
        "available": enabled(),
        "models": [{"model_id": MODEL, "label": "Gemini Live · Native Audio"}],
        "credits": CREDITS,
        "seconds": SECONDS,
        "voices": list(VOICES),
        "price_source": "https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-native-audio",
    }


class Start(BaseModel):
    voice_name: str
    model_id: str
    language: str = Field(default="ht", max_length=16)
    idempotency_key: str = Field(min_length=16, max_length=80)


def reserve(user_id, body):
    with Session.begin() as db:
        lock_sqlite_write(db)
        owner = db.scalar(select(User).where(User.id == user_id).with_for_update())
        existing = db.scalar(
            select(Job).where(Job.user_id == user_id, Job.idempotency_key == body.idempotency_key)
        )
        if existing:
            if existing.params.get("input_params", {}).get(
                "voice_name"
            ) != body.voice_name or not existing.params.get("input_params", {}).get("live_voice"):
                fail("IDEMPOTENCY_CONFLICT", 409)
            return existing.id
        if records.enabled():
            bank = wallets.snapshot(user_id)
            owner.balance, owner.reserved = bank["balance"], bank["reserved"]
        if owner.balance - owner.reserved < CREDITS:
            fail("INSUFFICIENT_CREDITS", 402)
        owner.reserved += CREDITS
        row = Job(
            user_id=user_id,
            studio="voice",
            title="HAYTILE AI · Live",
            prompt="",
            idempotency_key=body.idempotency_key,
            credits=CREDITS,
            lease_until=now() + timedelta(seconds=90),
            params={
                "model_id": MODEL,
                "input_params": {
                    "live_voice": True,
                    "chat_audio": True,
                    "voice_name": body.voice_name,
                    "language": body.language,
                },
            },
        )
        db.add(row)
        db.flush()
        db.add(
            Ledger(
                user_id=user_id,
                job_id=row.id,
                amount=0,
                kind="reserve",
                dedup_key=row.id + ":reserve:1",
            )
        )
        return row.id


@router.post("/v1/chat/live/sessions", status_code=201)
def start(body: Start, user=Depends(current)):
    if not enabled():
        fail("LIVE_VOICE_UNAVAILABLE", 503)
    if body.model_id != MODEL or body.voice_name not in VOICES:
        fail("MODEL_NOT_APPROVED", 409)
    limit("native-live:" + user.id, 10, 86400)
    limit("native-live-global", 50, 86400)
    job_id = reserve(user.id, body)
    return {
        "id": job_id,
        "socket_path": "/api/v1/chat/live/socket/" + job_id,
        "credits": CREDITS,
        "seconds": SECONDS,
    }


def claim(user_id, job_id):
    with Session.begin() as db:
        lock_sqlite_write(db)
        db.scalar(select(User).where(User.id == user_id).with_for_update())
        row = db.scalar(
            select(Job).where(Job.id == job_id, Job.user_id == user_id).with_for_update()
        )
        if (
            not row
            or not row.params.get("input_params", {}).get("live_voice")
            or row.params.get("model_id") != MODEL
            or row.credits != CREDITS
            or row.status != "queued"
            or aware(row.lease_until) <= now()
        ):
            fail("LIVE_VOICE_UNAVAILABLE", 409)
        row.status = "processing"
        row.progress = 15
        row.lease_until = now() + timedelta(seconds=SECONDS + 45)
        return dict(row.params["input_params"])


def settle(job_id, delivered):
    if not delivered:
        from .worker import finalize_failure

        finalize_failure(job_id, "LIVE_NO_AUDIO")
        return
    with Session.begin() as db:
        lock_sqlite_write(db)
        snap = db.get(Job, job_id)
        if not snap:
            return
        owner = db.scalar(select(User).where(User.id == snap.user_id).with_for_update())
        row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if row.status != "processing":
            return
        if records.enabled():
            bank = wallets.snapshot(owner.id)
            owner.balance, owner.reserved = bank["balance"], bank["reserved"]
        owner.reserved -= row.credits
        owner.balance -= row.credits
        row.status = "completed"
        row.progress = 100
        row.lease_until = None
        db.add(
            Ledger(
                user_id=owner.id,
                job_id=row.id,
                amount=-row.credits,
                kind="debit",
                dedup_key=row.id + ":debit",
            )
        )


def setup(params):
    policy = chat.SYSTEM + (
        " You are now in a live speech-to-speech conversation. Listen to the actual audio and respond naturally in the speaker’s language. "
        "Be concise, usually one or two sentences. Do not announce audio file generation or read Markdown. "
        "Haytile Topup is a separate product of the same owner. Only when someone asks for mobile top-ups, gift cards or game/connectivity digital products, "
        "you may suggest https://haytiles.com or https://app.haytiles.com, disclose common ownership, and never invent stock or prices. "
        "Never mention those commerce URLs for AI media requests. Use the studios within the AI app instead. "
        "Preferred interface language: " + params["language"]
    )
    return {
        "setup": {
            "model": "models/" + MODEL,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "maxOutputTokens": 1024,
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": params["voice_name"]}}
                },
            },
            "systemInstruction": {"parts": [{"text": policy}]},
            "contextWindowCompression": {
                "triggerTokens": 2048,
                "slidingWindow": {"targetTokens": 1024},
            },
        }
    }


@router.websocket("/api/v1/chat/live/socket/{job_id}")
async def socket(ws: WebSocket, job_id: str):
    # Cookie auth does not protect WebSocket handshakes against cross-site requests.
    if (
        ws.headers.get("origin") != os.environ.get("HAYTILE_PUBLIC_ORIGIN", "http://localhost:3000")
        or not enabled()
    ):
        await ws.close(code=1008)
        return
    try:
        user = await asyncio.to_thread(
            current, Request({"type": "http", "headers": ws.scope["headers"]})
        )
        params = await asyncio.to_thread(claim, user.id, job_id)
    except Exception:
        await ws.close(code=1008)
        return
    await ws.accept()
    delivered = False
    tasks = []
    try:
        # Key never enters the browser, URL, logs, or any persisted session document.
        async with connect(
            ENDPOINT,
            additional_headers={"x-goog-api-key": os.environ["HAYTILE_GEMINI_API_KEY"]},
            open_timeout=15,
            max_size=262144,
            max_queue=8,
            close_timeout=3,
        ) as upstream:
            await upstream.send(json.dumps(setup(params)))
            first = json.loads(await asyncio.wait_for(upstream.recv(), 15))
            if "setupComplete" not in first:
                raise ValueError("LIVE_SETUP_FAILED")
            await ws.send_json({"type": "ready", "seconds": SECONDS, "credits": CREDITS})
            started = time.monotonic()

            async def microphone():
                total = 0
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text"):
                        if message["text"] == "stop":
                            return
                        if message["text"] == "mute":
                            await upstream.send(
                                json.dumps({"realtimeInput": {"audioStreamEnd": True}})
                            )
                            continue
                        raise ValueError("LIVE_PROTOCOL")
                    pcm = message.get("bytes", b"")
                    total += len(pcm)
                    if (
                        not pcm
                        or len(pcm) > 6400
                        or len(pcm) % 2
                        or total > 32000 * (time.monotonic() - started + 1)
                    ):
                        raise ValueError("LIVE_AUDIO_LIMIT")
                    await upstream.send(
                        json.dumps(
                            {
                                "realtimeInput": {
                                    "audio": {
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": base64.b64encode(pcm).decode(),
                                    }
                                }
                            }
                        )
                    )

            async def speaker():
                nonlocal delivered
                usage = 0
                async for packet in upstream:
                    data = json.loads(packet)
                    if data.get("error"):
                        raise ValueError("LIVE_PROVIDER_ERROR")
                    usage += int(data.get("usageMetadata", {}).get("totalTokenCount", 0))
                    content = data.get("serverContent", {})
                    if content.get("interrupted"):
                        await ws.send_json({"type": "interrupted"})
                    for part in content.get("modelTurn", {}).get("parts", []):
                        inline = part.get("inlineData", {})
                        if inline.get("mimeType", "").startswith("audio/pcm") and inline.get(
                            "data"
                        ):
                            await ws.send_json(
                                {"type": "audio", "data": inline["data"], "rate": 24000}
                            )
                            if not delivered:
                                delivered = True
                                # Durable debit on first delivered audio; silence/setup failure refunds.
                                await asyncio.to_thread(settle, job_id, True)
                    if content.get("turnComplete"):
                        await ws.send_json({"type": "turn_complete"})
                    if usage >= MAX_USAGE:
                        await ws.send_json({"type": "ended", "reason": "LIVE_SESSION_LIMIT"})
                        return
                    if data.get("goAway"):
                        return

            tasks = [asyncio.create_task(microphone()), asyncio.create_task(speaker())]
            done, _ = await asyncio.wait(
                tasks, timeout=SECONDS, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
            await ws.send_json({"type": "ended", "reason": "LIVE_SESSION_LIMIT"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        # Never log upstream exception strings: these may include authentication data.
        try:
            await ws.send_json({"type": "error", "code": "LIVE_CONNECTION_FAILED"})
        except Exception:
            pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(settle, job_id, delivered)
        try:
            await ws.close()
        except Exception:
            pass
