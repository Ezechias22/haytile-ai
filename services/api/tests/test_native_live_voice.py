import asyncio
import base64
import json
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

from haytile import live_voice, providers, worker
from haytile.db import Asset, Job, Session, now

from .conftest import register
from .test_core import fund


class FakeLive:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.queue.put_nowait(json.dumps({"setupComplete": {}}))
        self.messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, message):
        data = json.loads(message)
        self.messages.append(data)
        if "realtimeInput" in data and "audio" in data["realtimeInput"]:
            self.queue.put_nowait(
                json.dumps(
                    {
                        "serverContent": {
                            "inputTranscription": {"text": "Must never become a chat message"},
                            "modelTurn": {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": "audio/pcm;rate=24000",
                                            "data": base64.b64encode(b"\x01\x00" * 240).decode(),
                                        }
                                    }
                                ]
                            },
                        }
                    }
                )
            )
            self.queue.put_nowait(json.dumps({"serverContent": {"interrupted": True}}))

    async def recv(self):
        return await self.queue.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()


def prepare(client, monkeypatch):
    monkeypatch.setenv("HAYTILE_LIVE_VOICE_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "offline-not-a-real-key")
    monkeypatch.setenv("HAYTILE_PUBLIC_ORIGIN", "http://localhost:3000")
    user, auth = register(client)
    fund(user["id"], 300)

    def forbidden(*a, **kw):
        raise AssertionError("Text/TTS transport must never be invoked")

    monkeypatch.setattr(providers, "generate", forbidden)
    body = {
        "voice_name": "Charon",
        "model_id": live_voice.MODEL,
        "language": "ht",
        "idempotency_key": str(uuid.uuid4()),
    }
    return user, auth, body


def test_native_stream_pcm_interrupts_and_debits_once_without_chat_or_asset(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    fake = FakeLive()
    monkeypatch.setattr(live_voice, "connect", lambda *a, **kw: fake)
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 70
    assert (
        client.post("/v1/chat/live/sessions", headers=auth, json=body).json()["id"] == session["id"]
    )
    assert not worker.run_once()  # The ordinary worker never claims native live reservations.
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x01\x00" * 1600)
        assert ws.receive_json()["type"] == "audio"
        assert ws.receive_json()["type"] == "interrupted"
        ws.send_text("stop")
        assert ws.receive_json()["type"] == "ended"
        assert ws.receive()["type"] == "websocket.close"
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 230 and wallet["reserved"] == 0
    live_voice.settle(session["id"], True)
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 230
    with Session() as db:
        assert db.query(Job).filter(Job.user_id == user["id"]).count() == 1
        assert db.query(Asset).filter(Asset.user_id == user["id"]).count() == 0
    setup = fake.messages[0]["setup"]
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert (
        setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        == "Charon"
    )
    assert "inputAudioTranscription" not in setup
    assert fake.messages[1]["realtimeInput"]["audio"]["mimeType"] == "audio/pcm;rate=16000"


def test_live_failure_refunds_without_external_generation(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)

    def denied(*a, **kw):
        raise OSError("Offline simulated provider refusal")

    monkeypatch.setattr(live_voice, "connect", denied)
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json() == {"type": "error", "code": "LIVE_CONNECTION_FAILED"}
        assert ws.receive()["type"] == "websocket.close"
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 300
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 0


def test_live_origin_ownership_and_single_claim(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            session["socket_path"], headers={**auth, "origin": "https://attacker.invalid"}
        ):
            pass
    _, other = register(client, "other-live@example.test")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            session["socket_path"], headers={**other, "origin": "http://localhost:3000"}
        ):
            pass
    live_voice.claim(user["id"], session["id"])
    with pytest.raises(HTTPException):
        live_voice.claim(user["id"], session["id"])
    live_voice.settle(session["id"], False)
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 0


def test_abandoned_native_reservation_expires_and_models_fail_closed(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    assert (
        client.post(
            "/v1/chat/live/sessions", headers=auth, json={**body, "model_id": "not-a-live-model"}
        ).status_code
        == 409
    )
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with Session.begin() as db:
        db.get(Job, session["id"]).lease_until = now() - timedelta(seconds=1)
    worker.run_once()
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 0
    monkeypatch.setenv("HAYTILE_LIVE_VOICE_ENABLED", "0")
    assert client.post("/v1/chat/live/sessions", headers=auth, json=body).status_code == 503
