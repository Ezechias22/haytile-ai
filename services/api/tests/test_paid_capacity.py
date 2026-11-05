from haytile import providers
from haytile.trials import trial_limit_code

from .conftest import register
from .test_core import configure, fund, job_request


def test_paid_music_does_not_use_the_free_daily_media_bucket(client, monkeypatch):
    configure(monkeypatch, "music", 5)
    monkeypatch.setenv("HAYTILE_DAILY_JOB_LIMIT", "1")
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_TRIAL_PER_STUDIO_PER_DAY", "2")
    user, auth = register(client)
    fund(user["id"], 50)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *a: (_ for _ in ()).throw(AssertionError("No generation during admission tests")),
    )
    for index in range(3):
        body = job_request("music", 5, key="paid-music-capacity-" + str(index))
        response = client.post("/v1/jobs", headers=auth, json=body)
        assert response.status_code == 202, response.text
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 50 and wallet["reserved"] == 15


def test_brief_burst_protection_is_distinct_and_never_calls_provider(client, monkeypatch):
    configure(monkeypatch, "music", 5)
    monkeypatch.setenv("HAYTILE_DAILY_PAID_JOB_LIMIT", "1")
    user, auth = register(client)
    fund(user["id"], 50)
    for index in range(6):
        assert (
            client.post(
                "/v1/jobs",
                headers=auth,
                json=job_request("music", 5, key="music-burst-" + str(index)),
            ).status_code
            == 202
        )
    second = client.post(
        "/v1/jobs", headers=auth, json=job_request("music", 5, key="music-burst-overflow")
    )
    assert second.status_code == 429 and second.json()["detail"] == "APP_BURST_LIMIT"
    assert len(client.get("/v1/jobs", headers=auth).json()) == 6
    wallet = client.get("/v1/wallet", headers=auth).json()
    assert wallet["balance"] == 50 and wallet["reserved"] == 30


def test_paid_firestore_backed_sqlite_does_not_apply_temporary_trial_limit(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from haytile.db import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_ACCOUNT_PROVIDER", "firestore")
    monkeypatch.setenv("HAYTILE_TRIAL_PER_STUDIO_PER_DAY", "0")
    with Session(engine) as db:
        assert trial_limit_code(db, "owned-fixture", "music", {}, 32) is None
        assert trial_limit_code(db, "owned-fixture", "text", {}, 0) == "TRIAL_STUDIO_LIMIT"
