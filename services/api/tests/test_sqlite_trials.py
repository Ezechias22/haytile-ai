import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from haytile import main, providers, worker
from haytile.db import Asset, Base, Model

from .conftest import register
from .test_core import job_request


@pytest.fixture
def temporary_trial(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "trial.db"),
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "Session", sessions)
    monkeypatch.setattr(worker, "Session", sessions)
    monkeypatch.setattr(main, "FREE_BETA", True)
    monkeypatch.setenv("HAYTILE_TRIAL_AI", "1")
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "fixture-not-a-real-key")
    with sessions.begin() as db:
        db.add(
            Model(
                studio="text",
                model_id="fixture-text",
                enabled=True,
                credits=0,
                price_source="https://example.test/price",
            )
        )
    yield sessions
    engine.dispose()


def test_zero_credit_sqlite_trial_persists_a_real_job_result(
    client, temporary_trial, monkeypatch
):
    _, h = register(client)
    monkeypatch.setattr(
        providers, "generate", lambda *_: (b"Fixture provider output", "text/plain")
    )
    response = client.post("/v1/jobs", json=job_request(credits=0), headers=h)
    assert response.status_code == 202, response.text
    assert worker.run_once()
    assert client.get("/v1/jobs", headers=h).json()[0]["status"] == "completed"
    assert (
        client.get("/v1/assets", headers=h).json()[0]["text"]
        == "Fixture provider output"
    )
    assert client.get("/v1/wallet", headers=h).json()["transactions"] == []
    assert client.get("/v1/runtime").json()["provider_generation_disabled"] is False


def test_sqlite_idempotent_admission_and_single_worker_claim(
    client, temporary_trial, monkeypatch
):
    _, h = register(client)

    def submit(_):
        return client.post("/v1/jobs", json=job_request(credits=0), headers=h)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert len({r.json()["id"] for r in responses}) == 1
    calls = []
    mutex = Lock()

    def generate(*_):
        with mutex:
            calls.append(1)
        time.sleep(0.1)
        return b"Only once", "text/plain"

    monkeypatch.setattr(providers, "generate", generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker.run_once(), range(2)))
    assert len(calls) == 1
    with temporary_trial() as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 1


def test_sqlite_trial_limits_and_paid_credit_model_refusal(client, temporary_trial):
    user, h = register(client)
    for index in range(2):
        r = client.post(
            "/v1/jobs",
            json=job_request(credits=0, key="trial-limit-" + str(index)),
            headers=h,
        )
        assert r.status_code == 202, r.text
    r = client.post(
        "/v1/jobs", json=job_request(credits=0, key="trial-limit-third"), headers=h
    )
    assert r.status_code == 429 and r.json()["detail"] == "TRIAL_STUDIO_LIMIT"
    with temporary_trial.begin() as db:
        db.get(Model, "text").credits = 1
    r = client.post(
        "/v1/jobs", json=job_request(credits=1, key="trial-paid-model"), headers=h
    )
    assert r.status_code == 409 and r.json()["detail"] == "PERSISTENT_POSTGRES_REQUIRED"
