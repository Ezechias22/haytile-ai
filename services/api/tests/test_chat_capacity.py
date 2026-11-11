import uuid
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as LocalSession

from haytile import main, providers, worker
from haytile.db import Base, RateLimit, Session, now
from haytile.trials import trial_limit_code

from .conftest import register
from .test_core import configure, fund, job_request


def chat_request(index=0, conversation=None):
    return {
        **job_request("text", 0, key="continuous-chat-" + str(index)),
        "params": {"chat": True, "conversation_id": conversation or str(uuid.uuid4())},
    }


def test_normal_chat_continues_past_legacy_daily_and_hourly_limits(client, monkeypatch):
    configure(monkeypatch, "text")
    monkeypatch.setenv("HAYTILE_CHAT_PER_DAY", "1")
    monkeypatch.setenv("HAYTILE_DAILY_CHAT_LIMIT", "1")
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    user, auth = register(client)
    clock = [now()]
    monkeypatch.setattr(main, "now", lambda: clock[0])
    with Session.begin() as db:
        for key in [
            "generation-chat-global",
            "chat-daily:" + user["id"],
            "generation:" + user["id"],
        ]:
            db.add(RateLimit(key=key, count=1000, reset_at=now() + timedelta(days=1)))
    calls = []

    def transport(*args, **kwargs):
        calls.append(True)
        return {"candidates": [{"content": {"parts": [{"text": "Continuing this conversation."}]}}]}

    monkeypatch.setattr(providers, "request", transport)
    conversation = str(uuid.uuid4())
    parent = None
    for index in range(35):
        clock[0] += timedelta(seconds=15)
        body = chat_request(index, conversation)
        body["params"]["parent_job_id"] = parent
        response = client.post("/v1/jobs", headers=auth, json=body)
        assert response.status_code == 202, response.text
        parent = response.json()["id"]
        assert worker.run_once()
    assert len(calls) == 35
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == wallet["reserved"] == 0


def test_chat_burst_is_brief_explicit_and_does_not_call_provider(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)

    def unexpected(*args, **kwargs):
        raise AssertionError("Admission must not call Google generation")

    monkeypatch.setattr(providers, "generate", unexpected)
    for index in range(6):
        response = client.post("/v1/jobs", headers=auth, json=chat_request(index))
        assert response.status_code == 202, response.text
    response = client.post("/v1/jobs", headers=auth, json=chat_request(7))
    assert response.status_code == 429 and response.json()["detail"] == "APP_BURST_LIMIT"


def test_music_queue_does_not_block_chat_but_each_conversation_waits_for_its_reply(
    client, monkeypatch
):
    configure(monkeypatch, "music", 5)
    configure(monkeypatch, "text")
    user, auth = register(client)
    fund(user["id"], 50)
    for index in range(3):
        assert (
            client.post(
                "/v1/jobs",
                headers=auth,
                json=job_request("music", 5, key="music-queue-" + str(index)),
            ).status_code
            == 202
        )
    conversation = str(uuid.uuid4())
    assert (
        client.post("/v1/jobs", headers=auth, json=chat_request(0, conversation)).status_code == 202
    )
    response = client.post("/v1/jobs", headers=auth, json=chat_request(1, conversation))
    assert response.status_code == 409 and response.json()["detail"] == "CHAT_MESSAGE_PROCESSING"


def test_firestore_chat_does_not_inherit_temporary_trial_ceiling(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("HAYTILE_ACCOUNT_PROVIDER", "firestore")
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_CHAT_PER_DAY", "0")
    monkeypatch.setenv("HAYTILE_TRIAL_PER_STUDIO_PER_DAY", "0")
    with LocalSession(engine) as db:
        assert trial_limit_code(db, "owner", "text", {"chat": True}, 0) is None
        assert trial_limit_code(db, "owner", "text", {}, 0) == "TRIAL_STUDIO_LIMIT"
