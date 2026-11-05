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
from websockets.exceptions import ConnectionClosed

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
MAX_USAGE = 32000
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
        "continuous": True,
        "billing": "per_started_minute",
        "voices": list(VOICES),
        "price_source": "https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-native-audio",
    }


class Start(BaseModel):
    voice_name: str
    model_id: str
    language: str = Field(default="ht", max_length=16)
    idempotency_key: str = Field(min_length=16, max_length=80)


def reserve(user_id, body, parent_job_id=None):
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
            if bank.get("billing_hold"):
                fail("BILLING_REVIEW_REQUIRED", 403)
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
                **({"native_parent_id": parent_job_id} if parent_job_id else {}),
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
    limit("native-live-start-burst:" + user.id, 6, 10, "APP_BURST_LIMIT")
    job_id = reserve(user.id, body)
    return {
        "id": job_id,
        "socket_path": "/api/v1/chat/live/socket/" + job_id,
        "credits": CREDITS,
        "seconds": SECONDS,
    }


def claim(user_id, job_id, allow_child=False):
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
            or (row.params.get("native_parent_id") and not allow_child)
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
        if row.status == "completed":
            return True
        if row.status != "processing":
            return False
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
    return True


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
            "sessionResumption": {},
            "contextWindowCompression": {
                "triggerTokens": 2048,
                "slidingWindow": {"targetTokens": 1024},
            },
        }
    }


def charge_period(user_id, root_id, period, params):
    """A deterministic child reservation/debit; reconnects do not create periods."""
    body = Start(
        voice_name=params["voice_name"],
        model_id=MODEL,
        language=params["language"],
        idempotency_key=f"live:{root_id}:{period}",
    )
    with Session() as db:
        existing = db.scalar(
            select(Job).where(Job.user_id == user_id, Job.idempotency_key == body.idempotency_key)
        )
        if existing and existing.status == "completed":
            return
        parent = db.get(Job, root_id)
        if (
            not parent
            or parent.user_id != user_id
            or not parent.params.get("native_call_active_until")
        ):
            fail("LIVE_VOICE_UNAVAILABLE", 409)
        from datetime import datetime

        if datetime.fromisoformat(parent.params["native_call_active_until"]) <= now():
            fail("LIVE_VOICE_UNAVAILABLE", 409)
    jid = reserve(user_id, body, parent_job_id=root_id)
    with Session() as db:
        row = db.get(Job, jid)
        if row and row.status == "completed":
            return
    # A competing/retried period must never cancel another claimant's charge.
    claim(user_id, jid, allow_child=True)
    if not settle(jid, True):
        fail("LIVE_VOICE_UNAVAILABLE", 409)


def touch_call(job_id, active):
    with Session.begin() as db:
        lock_sqlite_write(db)
        row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not row or (active and (row.status == "failed" or row.params.get("native_call_closed"))):
            return False
        row.params = {
            **row.params,
            "native_call_active_until": (now() + timedelta(seconds=90)).isoformat()
            if active
            else None,
        }
        if not active:
            row.params = {**row.params, "native_call_closed": True}
        if active and row.status == "processing":
            row.lease_until = now() + timedelta(seconds=90)
        return True


@router.websocket("/api/v1/chat/live/socket/{job_id}")
async def socket(ws: WebSocket, job_id: str):
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
    input_sent = False
    stopping = asyncio.Event()
    first_audio = asyncio.Event()
    ready = asyncio.Event()
    flow = asyncio.Event()
    flow.set()
    meter_lock = asyncio.Lock()
    upstream = None
    period_tokens = 0

    async def ready_message():
        if flow.is_set():
            await ws.send_json(
                {"type": "ready", "seconds": SECONDS, "credits": CREDITS, "continuous": True}
            )
        else:
            await ws.send_json({"type": "throttled"})

    async def heartbeat():
        while True:
            if not await asyncio.to_thread(touch_call, job_id, True):
                raise ValueError("LIVE_VOICE_UNAVAILABLE")
            await asyncio.sleep(30)

    async def microphone():
        nonlocal input_sent
        allowance = 64000.0
        previous = time.monotonic()
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect" or message.get("text") == "stop":
                stopping.set()
                return
            if message.get("text"):
                if message["text"] != "mute":
                    raise ValueError("LIVE_PROTOCOL")
                if ready.is_set() and upstream is not None:
                    try:
                        connection = upstream
                        await connection.send(
                            json.dumps({"realtimeInput": {"audioStreamEnd": True}})
                        )
                    except ConnectionClosed:
                        if upstream is connection:
                            ready.clear()
                continue
            pcm = message.get("bytes", b"")
            instant = time.monotonic()
            allowance = min(64000.0, allowance + 32000 * (instant - previous))
            previous = instant
            if not pcm or len(pcm) > 6400 or len(pcm) % 2 or len(pcm) > allowance:
                raise ValueError("LIVE_AUDIO_LIMIT")
            allowance -= len(pcm)
            # A reconnect/rate pause never accumulates raw microphone recordings.
            if ready.is_set() and flow.is_set() and upstream is not None:
                try:
                    connection = upstream
                    await connection.send(
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
                    input_sent = True
                except ConnectionClosed:
                    if upstream is connection:
                        ready.clear()

    async def reset_flow():
        nonlocal period_tokens
        period_tokens = 0
        was_paused = not flow.is_set()
        flow.set()
        if was_paused and ready.is_set():
            await ready_message()

    async def billing():
        nonlocal delivered
        # Failed setup is refundable; an open, input-streaming call is metered
        # even if the user keeps speaking for a minute without waiting for a reply.
        while not first_audio.is_set():
            try:
                await asyncio.wait_for(first_audio.wait(), SECONDS)
            except asyncio.TimeoutError:
                async with meter_lock:
                    if stopping.is_set():
                        return
                    if input_sent and not delivered:
                        if not await asyncio.to_thread(settle, job_id, True):
                            raise ValueError("LIVE_VOICE_UNAVAILABLE")
                        delivered = True
                        first_audio.set()
                        await ws.send_json({"type": "billing", "credits": CREDITS, "period": 1})
                await reset_flow()
        period = 1
        while True:
            await asyncio.sleep(SECONDS)
            async with meter_lock:
                if stopping.is_set():
                    return
                if not enabled():
                    await ws.send_json({"type": "ended", "reason": "LIVE_VOICE_UNAVAILABLE"})
                    return
                period += 1
                try:
                    await asyncio.to_thread(charge_period, user.id, job_id, period, params)
                except Exception as exc:
                    reason = getattr(exc, "detail", None)
                    await ws.send_json(
                        {
                            "type": "ended",
                            "reason": reason
                            if reason in ("INSUFFICIENT_CREDITS", "BILLING_REVIEW_REQUIRED")
                            else "LIVE_CONNECTION_FAILED",
                        }
                    )
                    return
                await ws.send_json({"type": "billing", "credits": CREDITS, "period": period})
                await reset_flow()

    async def provider():
        nonlocal upstream, delivered, period_tokens
        resume_handle = None
        attempts = 0
        connected_once = False
        while not stopping.is_set():
            ready.clear()
            if connected_once:
                await ws.send_json({"type": "reconnecting"})
            config = setup(params)
            if resume_handle:
                config["setup"]["sessionResumption"] = {"handle": resume_handle}
            healthy = False
            try:
                async with connect(
                    ENDPOINT,
                    additional_headers={"x-goog-api-key": os.environ["HAYTILE_GEMINI_API_KEY"]},
                    open_timeout=15,
                    max_size=262144,
                    max_queue=8,
                    close_timeout=3,
                ) as connection:
                    upstream = connection
                    await connection.send(json.dumps(config))
                    first = json.loads(await asyncio.wait_for(connection.recv(), 15))
                    if "setupComplete" not in first:
                        raise ValueError("LIVE_SETUP_FAILED")
                    connected_once = True
                    ready.set()
                    await ready_message()
                    go_away = False
                    speaking = False
                    async for packet in connection:
                        data = json.loads(packet)
                        if data.get("error"):
                            raise ValueError("LIVE_PROVIDER_ERROR")
                        update = data.get("sessionResumptionUpdate", {})
                        if update.get("resumable") and update.get("newHandle"):
                            resume_handle = update["newHandle"]
                        if data.get("goAway"):
                            go_away = True
                        period_tokens += int(
                            data.get("usageMetadata", {}).get("totalTokenCount", 0)
                        )
                        content = data.get("serverContent", {})
                        if content:
                            healthy = True
                        if content.get("interrupted"):
                            speaking = False
                            await ws.send_json({"type": "interrupted"})
                        for part in content.get("modelTurn", {}).get("parts", []):
                            inline = part.get("inlineData", {})
                            if inline.get("mimeType", "").startswith("audio/pcm") and inline.get(
                                "data"
                            ):
                                async with meter_lock:
                                    if stopping.is_set():
                                        return
                                    if not delivered:
                                        charged = await asyncio.to_thread(settle, job_id, True)
                                        if not charged:
                                            raise ValueError("LIVE_VOICE_UNAVAILABLE")
                                        delivered = True
                                        first_audio.set()
                                        await ws.send_json(
                                            {"type": "billing", "credits": CREDITS, "period": 1}
                                        )
                                    await ws.send_json(
                                        {"type": "audio", "data": inline["data"], "rate": 24000}
                                    )
                                speaking = True
                        if content.get("turnComplete"):
                            speaking = False
                            await ws.send_json({"type": "turn_complete"})
                        if period_tokens >= MAX_USAGE and flow.is_set():
                            flow.clear()
                            await ws.send_json({"type": "throttled"})
                        if go_away and not speaking and resume_handle:
                            break
            except ConnectionClosed:
                pass
            finally:
                ready.clear()
                upstream = None
            if stopping.is_set():
                return
            attempts = 0 if healthy else attempts + 1
            if not resume_handle or attempts >= 3:
                raise ValueError("LIVE_CONNECTION_FAILED")
            await asyncio.sleep(min(0.25 * max(attempts, 1), 2))

    tasks = []
    try:
        tasks = [
            asyncio.create_task(microphone()),
            asyncio.create_task(provider()),
            asyncio.create_task(billing()),
            asyncio.create_task(heartbeat()),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if stopping.is_set():
            await ws.send_json({"type": "ended", "reason": "USER_STOP"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        # Upstream exception strings can contain credentials; never expose/log them.
        try:
            await ws.send_json({"type": "error", "code": "LIVE_CONNECTION_FAILED"})
        except Exception:
            pass
    finally:
        stopping.set()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.to_thread(settle, job_id, delivered)
        except Exception:
            # Preserve the lease for existing durable reconciliation; no blind debit.
            pass
        try:
            await asyncio.to_thread(touch_call, job_id, False)
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
