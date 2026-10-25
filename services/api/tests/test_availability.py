import pytest

from haytile import bootstrap, providers, worker
from haytile.db import Job, Session

from .conftest import register


def test_paused_generation_cannot_admit_or_execute_provider_work(client, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "0")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "0")
    monkeypatch.setattr(
        providers, "generate", lambda *a: pytest.fail("Paid generation was called")
    )
    user, headers = register(client)
    runtime = client.get("/v1/runtime").json()
    assert runtime["generation_paused"] and not runtime["background_processing_enabled"]
    assert not any(m["available"] for m in client.get("/v1/models").json())
    result = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "studio": "image",
            "title": "Must not run",
            "prompt": "A garden",
            "params": {},
            "idempotency_key": "paused-job-admission",
            "confirmed_credits": 0,
        },
    )
    assert result.status_code == 503 and result.json()["detail"] == "AI_SERVICE_PAUSED"
    assert client.get("/v1/jobs", headers=headers).json() == []
    with Session.begin() as db:
        db.add(
            Job(
                user_id=user["id"],
                studio="image",
                title="Previously queued",
                prompt="A garden",
                params={},
                credits=0,
                idempotency_key="paused-existing-job",
            )
        )
    assert worker.run_once() is False
    assert client.get("/v1/jobs", headers=headers).json()[0]["status"] == "queued"
    assert client.get("/v1/wallet", headers=headers).json()["reserved"] == 0


def test_paused_startup_does_not_probe_or_activate_ai_models(monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "0")
    monkeypatch.setenv(
        "HAYTILE_MODEL_CONFIG", '[{"studio":"image","model_id":"fixture"}]'
    )
    monkeypatch.setattr(
        providers, "discover", lambda: pytest.fail("Provider was contacted")
    )
    bootstrap.configure_models()
