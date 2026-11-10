import uuid
from datetime import timedelta

from haytile import providers, worker
from haytile.db import now

from .conftest import register
from .test_core import configure, job_request


def fix(**extra):
    return {
        "latitude": 18.543291,
        "longitude": -72.343917,
        "accuracy_m": 7.2,
        "captured_at": now().isoformat(),
        **extra,
    }


def test_preference_persists_is_private_and_rejects_updates_after_revocation(client):
    _, auth = register(client)
    assert client.get("/v1/chat/location", headers=auth).json()["known"] is False
    result = client.patch("/v1/chat/location", headers=auth, json=fix(authorize=True))
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["enabled"] is True and saved["position"]["latitude"] == 18.543291
    assert client.get("/v1/chat/location", headers=auth).json() == saved
    assert client.get("/v1/projects", headers=auth).json() == []
    _, other = register(client, "another-device-owner@example.test")
    assert client.get("/v1/chat/location", headers=other).json()["position"] is None
    client.cookies.clear()
    assert client.get("/v1/chat/location").status_code == 401
    older = fix(
        captured_at=(now() - timedelta(seconds=30)).isoformat(), consent_version=saved["version"]
    )
    assert (
        client.patch("/v1/chat/location", headers=auth, json=older).json()["position"]
        == saved["position"]
    )
    revoked = client.delete("/v1/chat/location", headers=auth).json()
    assert revoked["known"] is True and revoked["enabled"] is False and revoked["position"] is None
    assert (
        client.patch(
            "/v1/chat/location", headers=auth, json=fix(consent_version=saved["version"])
        ).status_code
        == 409
    )
    assert client.get("/v1/chat/location", headers=auth).json()["enabled"] is False
    enabled = client.patch("/v1/chat/location", headers=auth, json=fix(authorize=True)).json()
    assert enabled["enabled"] is True and enabled["version"] > saved["version"]


def test_remembered_location_reused_with_accuracy_and_no_repeat_permission(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    assert (
        client.patch("/v1/chat/location", headers=auth, json=fix(authorize=True)).status_code == 200
    )
    calls = []

    def transport(method, path, payload=None, **kwargs):
        calls.append(payload)
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Here is nearby help. [HAYTILE_REQUEST_LOCATION]"}]
                    }
                }
            ]
        }

    monkeypatch.setattr(providers, "request", transport)
    conversation = str(uuid.uuid4())

    def send(parent=None):
        body = {
            **job_request("text", 0, key=str(uuid.uuid4()), prompt="Find help nearby"),
            "params": {"chat": True, "conversation_id": conversation, "parent_job_id": parent},
        }
        result = client.post("/v1/jobs", headers=auth, json=body)
        assert result.status_code == 202, result.text
        assert worker.run_once()
        return result.json()["id"]

    parent = send()
    parent = send(parent)
    for payload in calls:
        text = str(payload["contents"][-1])
        assert "18.543291" in text and "-72.343917" in text and "7.2 meters" in text
        assert "Captured at:" in text
    rows = client.get("/v1/chat/conversations/" + conversation, headers=auth).json()
    assert all(not row["params"]["chat_location_requested"] for row in rows)
    assert all("[HAYTILE_REQUEST_LOCATION]" not in row["reply"] for row in rows)
    client.delete("/v1/chat/location", headers=auth)
    send(parent)
    assert "18.543291" not in str(calls[-1]["contents"])
    assert "disabled" in str(calls[-1]["systemInstruction"])
    assert not client.get("/v1/chat/conversations/" + conversation, headers=auth).json()[-1][
        "params"
    ]["chat_location_requested"]


def test_invalid_or_unapproved_fixes_cannot_enable_location(client):
    _, auth = register(client)
    assert client.patch("/v1/chat/location", headers=auth, json=fix()).status_code == 409
    for data in [
        fix(authorize=True, accuracy_m=-1),
        fix(authorize=True, latitude=91),
        fix(authorize=True, captured_at=(now() - timedelta(hours=1)).isoformat()),
    ]:
        assert client.patch("/v1/chat/location", headers=auth, json=data).status_code in (400, 422)
    assert client.get("/v1/chat/location", headers=auth).json()["enabled"] is False


def test_queued_fix_is_not_sent_after_sharing_is_stopped(client, monkeypatch):
    configure(monkeypatch, "text")
    _, auth = register(client)
    position = fix(authorize=True)
    saved = client.patch("/v1/chat/location", headers=auth, json=position).json()
    calls = []

    def transport(method, path, payload=None, **kwargs):
        calls.append(payload)
        return {"candidates": [{"content": {"parts": [{"text": "Please enter your city."}]}}]}

    monkeypatch.setattr(providers, "request", transport)
    body = {
        **job_request("text", 0, key=str(uuid.uuid4()), prompt="Find nearby help"),
        "params": {
            "chat": True,
            "conversation_id": str(uuid.uuid4()),
            "location": saved["position"],
            "location_consent_version": saved["version"],
        },
    }
    assert client.post("/v1/jobs", headers=auth, json=body).status_code == 202
    assert client.delete("/v1/chat/location", headers=auth).status_code == 200
    assert worker.run_once()
    assert "18.543291" not in str(calls[0]["contents"])
