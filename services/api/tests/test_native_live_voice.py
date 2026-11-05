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
        assert ws.receive_json() == {"type": "billing", "credits": 70, "period": 1}
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


def receive_type(ws, kind):
    for _ in range(30):
        packet = ws.receive_json()
        if packet["type"] == kind:
            return packet
        assert packet["type"] not in ("error", "ended"), packet
    raise AssertionError("Expected packet not received: " + kind)


def test_call_continues_across_billing_minutes_until_user_stops(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    monkeypatch.setattr(live_voice, "SECONDS", 0.05)
    fake = FakeLive()
    monkeypatch.setattr(live_voice, "connect", lambda *a, **kw: fake)
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json()["continuous"]
        ws.send_bytes(b"\x01\x00" * 1600)
        assert receive_type(ws, "billing")["period"] == 1
        assert receive_type(ws, "audio")["data"]
        assert receive_type(ws, "billing")["period"] == 2
        assert receive_type(ws, "billing")["period"] == 3
        ws.send_text("stop")
        assert ws.receive_json() == {"type": "ended", "reason": "USER_STOP"}
        assert ws.receive()["type"] == "websocket.close"
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 90 and wallet["reserved"] == 0
    live_voice.charge_period(
        user["id"], session["id"], 2, {"voice_name": "Charon", "language": "ht"}
    )
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 90
    with Session() as db:
        rows = db.query(Job).filter(Job.user_id == user["id"]).all()
        assert len(rows) == 3 and all(row.status == "completed" for row in rows)
        assert db.get(Job, session["id"]).params["native_call_active_until"] is None


def test_continuation_stops_for_insufficient_credits_not_one_minute_timer(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    fund(user["id"], 70)
    monkeypatch.setattr(live_voice, "SECONDS", 0.05)
    monkeypatch.setattr(live_voice, "connect", lambda *a, **kw: FakeLive())
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x01\x00" * 1600)
        ended = None
        for _ in range(10):
            packet = ws.receive_json()
            if packet["type"] == "ended":
                ended = packet
                break
        assert ended == {"type": "ended", "reason": "INSUFFICIENT_CREDITS"}
        assert ws.receive()["type"] == "websocket.close"
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == wallet["reserved"] == 0


def test_provider_rotation_resumes_same_voice_without_new_charge(client, monkeypatch):
    user, auth, body = prepare(client, monkeypatch)
    first, second = FakeLive(), FakeLive()
    first.queue.put_nowait(
        json.dumps(
            {"sessionResumptionUpdate": {"resumable": True, "newHandle": "offline-resume-token"}}
        )
    )
    first.queue.put_nowait(json.dumps({"goAway": {"timeLeft": "0s"}}))
    connections = iter([first, second])
    monkeypatch.setattr(live_voice, "connect", lambda *a, **kw: next(connections))
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        assert ws.receive_json()["type"] == "reconnecting"
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x01\x00" * 1600)
        assert receive_type(ws, "billing")["period"] == 1
        assert receive_type(ws, "audio")["data"]
        ws.send_text("stop")
        assert receive_type(ws, "ended")["reason"] == "USER_STOP"
    assert second.messages[0]["setup"]["sessionResumption"]["handle"] == "offline-resume-token"
    assert (
        second.messages[0]["setup"]["generationConfig"]["speechConfig"]["voiceConfig"][
            "prebuiltVoiceConfig"
        ]["voiceName"]
        == "Charon"
    )
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 230


def test_rate_guard_keeps_call_open_and_resumes_next_period(client, monkeypatch):
    _, auth, body = prepare(client, monkeypatch)
    monkeypatch.setattr(live_voice, "SECONDS", 0.1)
    monkeypatch.setattr(live_voice, "MAX_USAGE", 1)
    fake = FakeLive()
    monkeypatch.setattr(live_voice, "connect", lambda *a, **kw: fake)
    session = client.post("/v1/chat/live/sessions", headers=auth, json=body).json()
    with client.websocket_connect(
        session["socket_path"], headers={**auth, "origin": "http://localhost:3000"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x01\x00" * 1600)
        receive_type(ws, "audio")
        # Send usage metadata after the first audible response.
        asyncio.run_coroutine_threadsafe(
            fake.queue.put(json.dumps({"usageMetadata": {"totalTokenCount": 2}})),
            client.portal.call(asyncio.get_running_loop),
        ).result()
        receive_type(ws, "throttled")
        assert receive_type(ws, "billing")["period"] == 2
        assert receive_type(ws, "ready")["continuous"]
        ws.send_text("stop")
        assert receive_type(ws, "ended")["reason"] == "USER_STOP"
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 160
