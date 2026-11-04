import io
import uuid
import wave

from sqlalchemy import select

from haytile import chat_cleanup, providers, storage, worker
from haytile.db import Asset, Job, Model, Project, Session

from .conftest import register
from .test_core import configure, fund, job_request


def setup_voice(client, monkeypatch, cap=6):
    configure(monkeypatch, "text", 0)
    with Session.begin() as db:
        db.add(
            Model(
                studio="voice",
                model_id="offline-voice",
                enabled=True,
                credits=3,
                price_source="https://example.test",
            )
        )
    user, auth = register(client)
    fund(user["id"], 30)
    cid = str(uuid.uuid4())
    reply = "Yon repons kout."
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(b"\x01\x00" * 2400)

    def fake(studio, model, prompt, params):
        return (reply.encode(), "text/plain") if studio == "text" else (buf.getvalue(), "audio/wav")

    monkeypatch.setattr(providers, "generate", fake)
    parent = client.post(
        "/v1/jobs",
        headers=auth,
        json={**job_request("text", 0), "params": {"chat": True, "conversation_id": cid}},
    )
    assert parent.status_code == 202
    assert worker.run_once()
    start = client.post(
        "/v1/chat/voice-sessions",
        headers=auth,
        json={
            "conversation_id": cid,
            "model_id": "offline-voice",
            "voice_name": "Puck",
            "credit_cap": cap,
            "confirmed_per_reply": 3,
        },
    )
    assert start.status_code == 201, start.text
    session = start.json()
    body = {
        **job_request("voice", 3, key="voice-session-request1", prompt=reply),
        "model_id": "offline-voice",
        "params": {
            "chat_audio": True,
            "conversation_id": cid,
            "parent_message_id": parent.json()["id"],
            "voice_name": "Puck",
            "voice_session_id": session["id"],
            "session_model_id": "offline-voice",
        },
    }
    return user, auth, cid, session, body


def test_voice_session_enforces_budget_settings_owner_and_close(client, monkeypatch):
    user, auth, cid, session, body = setup_voice(client, monkeypatch)
    assert client.get("/v1/projects", headers=auth).json() == []
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 0
    assert (
        client.put(
            "/v1/projects/" + session["id"],
            headers=auth,
            json={"title": "tamper", "version": 1, "document": {}},
        ).status_code
        == 404
    )
    assert client.delete("/v1/projects/" + session["id"], headers=auth).status_code == 404
    _, stranger = register(client, "other-session@example.test")
    assert (
        client.get("/v1/chat/voice-sessions/" + session["id"], headers=stranger).status_code == 404
    )
    assert (
        client.post(
            "/v1/jobs",
            headers=auth,
            json={**body, "params": {**body["params"], "voice_name": "Kore"}},
        ).status_code
        == 409
    )
    first = client.post("/v1/jobs", headers=auth, json=body)
    assert first.status_code == 202, first.text
    assert client.post("/v1/jobs", headers=auth, json=body).json()["id"] == first.json()["id"]
    second = client.post(
        "/v1/jobs", headers=auth, json={**body, "idempotency_key": "voice-session-request2"}
    )
    assert second.status_code == 202
    denied = client.post(
        "/v1/jobs", headers=auth, json={**body, "idempotency_key": "voice-session-request3"}
    )
    assert denied.status_code == 409 and denied.json()["detail"] == "VOICE_SESSION_BUDGET_REACHED"
    assert (
        client.get("/v1/chat/voice-sessions/" + session["id"], headers=auth).json()["remaining"]
        == 0
    )
    assert client.get("/v1/wallet", headers=auth).json()["reserved"] == 6
    assert worker.run_once() and worker.run_once()
    bank = client.get("/v1/wallet", headers=auth).json()
    assert bank["balance"] == 24 and bank["reserved"] == 0
    assert (
        client.post("/v1/chat/voice-sessions/" + session["id"] + "/stop", headers=auth).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/jobs", headers=auth, json={**body, "idempotency_key": "voice-after-stop"}
        ).json()["detail"]
        == "VOICE_SESSION_ENDED"
    )


def test_failed_speech_refunds_session_allocation_exactly_once(client, monkeypatch):
    _, auth, _, session, body = setup_voice(client, monkeypatch)
    job = client.post("/v1/jobs", headers=auth, json=body).json()

    def failed(*args):
        raise providers.ProviderError("PROVIDER_REFUSED_OR_EMPTY")

    monkeypatch.setattr(providers, "generate", failed)
    assert worker.run_once()
    worker.finalize_failure(job["id"], "duplicate failure")
    assert (
        client.get("/v1/chat/voice-sessions/" + session["id"], headers=auth).json()["remaining"]
        == 6
    )
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 30
    assert client.post("/v1/jobs/" + job["id"] + "/retry", headers=auth).status_code == 200
    assert (
        client.get("/v1/chat/voice-sessions/" + session["id"], headers=auth).json()["remaining"]
        == 3
    )


def test_delete_chat_keeps_other_content_and_handles_private_cleanup_failure(client, monkeypatch):
    _, auth, cid, session, body = setup_voice(client, monkeypatch)
    _, other = register(client, "delete-other@example.test")
    voice = client.post("/v1/jobs", headers=auth, json=body)
    assert voice.status_code == 202
    assert (
        client.delete("/v1/chat/conversations/" + cid, headers=auth).json()["detail"]
        == "CHAT_STILL_PROCESSING"
    )
    assert client.delete("/v1/chat/conversations/" + cid, headers=other).status_code == 200
    assert len(client.get("/v1/chat/conversations", headers=auth).json()) == 1
    assert worker.run_once()
    keep = client.post(
        "/v1/assets/text", headers=auth, json={"title": "Keep me", "text": "A separate document"}
    ).json()
    with Session() as db:
        deleted = list(db.scalars(select(Asset).where(Asset.job_id.is_not(None))))
        keys = [a.key for a in deleted]
    original = storage.delete

    def unavailable(*args):
        raise RuntimeError("offline cleanup failure")

    monkeypatch.setattr(storage, "delete", unavailable)
    removed = client.delete("/v1/chat/conversations/" + cid, headers=auth)
    assert removed.status_code == 200 and removed.json()["media_cleanup_pending"]
    assert client.get("/v1/chat/conversations", headers=auth).json() == []
    assert client.get("/v1/chat/conversations/" + cid, headers=auth).json() == []
    assert client.get("/v1/projects", headers=auth).json() == []
    assert [a["id"] for a in client.get("/v1/assets", headers=auth).json()] == [keep["id"]]
    monkeypatch.setattr(storage, "delete", original)
    assert chat_cleanup.run_once()
    with Session() as db:
        assert db.scalar(select(Project)) is None
        assert db.scalar(select(Job)) is None
    for key in keys:
        import pytest

        with pytest.raises(FileNotFoundError):
            storage.get(key)
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 27


def test_topup_scope_does_not_leak_commerce_links_into_media_answers():
    from haytile.chat import system_for, topup_relevant

    for prompt in [
        "Kreye yon videyo pou mwen",
        "Je veux créer une image",
        "Write a song",
        "How do I recharge Gemini API credits?",
        "Create a video about gift cards",
        "How do I recharge a laptop battery?",
        "Plan a data pipeline",
    ]:
        assert not topup_relevant(prompt)
        policy = system_for(prompt)
        assert "https://haytile-ai.onrender.com" in policy
        assert "https://app.haytiles.com" not in policy and "https://haytiles.com" not in policy
    for prompt in [
        "Ki app pou rechaj mobil?",
        "Where can I buy a Steam gift card?",
        "Preciso de uma recarga",
        "I need an eSIM data plan",
    ]:
        assert topup_relevant(prompt)
        policy = system_for(prompt)
        assert "https://app.haytiles.com" in policy and "another product" in policy


def test_voice_start_without_budget_uses_available_balance(client, monkeypatch):
    user, auth, cid, session, body = setup_voice(client, monkeypatch)
    started = client.post(
        '/v1/chat/voice-sessions', headers=auth,
        json={'conversation_id': cid, 'model_id': 'offline-voice',
              'voice_name': 'Charon', 'confirmed_per_reply': 3},
    )
    assert started.status_code == 201, started.text
    assert started.json()['credit_cap'] == 30
    assert started.json()['remaining'] == 30
    assert client.get('/v1/wallet', headers=auth).json()['reserved'] == 0
    assert client.post('/v1/chat/voice-sessions/'+started.json()['id']+'/stop', headers=auth).status_code == 200
