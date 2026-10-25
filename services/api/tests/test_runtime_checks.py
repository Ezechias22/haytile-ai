import pytest

from haytile.db import Model, Session
from haytile.runtime_checks import configuration_checks, require_durable_runtime

from .conftest import register


def test_production_rejects_temporary_runtime_but_explicit_beta_remains_available(monkeypatch):
    monkeypatch.setenv("HAYTILE_ENV", "production")
    monkeypatch.delenv("HAYTILE_FREE_BETA", raising=False)
    with pytest.raises(RuntimeError, match="postgresql"):
        require_durable_runtime("sqlite")
    monkeypatch.setenv("HAYTILE_FREE_BETA", "1")
    require_durable_runtime("sqlite")


def test_production_checks_reject_insecure_storage_and_implicit_signing_key():
    env = {
        "HAYTILE_PUBLIC_ORIGIN": "https://haytile.example",
        "STORAGE_BUCKET": "private-fixture",
        "STORAGE_ENDPOINT": "http://s3.example",
    }
    checks = configuration_checks(env, "postgresql")
    assert checks["postgresql"] and checks["https_origin"]
    assert not checks["storage_tls"] and not checks["explicit_signing_key"]


def test_durable_database_does_not_remove_operator_trial_spend_limits(client, monkeypatch):
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "fixture")
    with Session.begin() as db:
        db.add(
            Model(
                studio="video",
                model_id="fixture",
                enabled=True,
                credits=0,
                price_source="https://example.test",
            )
        )
    _, headers = register(client)
    assert client.get("/v1/runtime").json()["trial_max_video_seconds"] == 8
    result = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "studio": "video",
            "title": "Over trial limit",
            "prompt": "A garden",
            "params": {"duration": 16, "aspect": "16:9"},
            "idempotency_key": "persistent-trial-test",
            "confirmed_credits": 0,
        },
    )
    assert result.status_code == 429
    assert result.json()["detail"] == "TRIAL_VIDEO_DURATION_LIMIT"
