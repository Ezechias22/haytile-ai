from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from haytile import accounts, providers, wallets, worker
from haytile.db import Job, Session, now
from haytile.main import app

from .conftest import register
from .test_account_persistence import FirestoreFixture, wipe_local
from .test_core import configure, job_request


@pytest.fixture
def remote(monkeypatch):
    fake = FirestoreFixture()
    monkeypatch.setenv("HAYTILE_ACCOUNT_PROVIDER", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("FIREBASE_DATABASE_ID", "default")
    monkeypatch.setattr(accounts.transport, "request", fake)
    return fake


def setup(client):
    owner, admin = register(client, "owner-wallet@example.test")
    accounts.change(owner["id"], {"role": "admin"})
    target, ordinary = register(client, "recipient-wallet@example.test")
    return owner, admin, target, ordinary


def test_grant_plan_and_history_survive_sql_loss(remote):
    with TestClient(app) as c:
        owner, admin, target, ordinary = setup(c)
        grant = {
            "email": target["email"],
            "amount": 100,
            "idempotency_key": "wallet-grant-123",
        }
        assert (
            c.post("/v1/admin/credits", headers=ordinary, json=grant).status_code == 403
        )

        def post():
            return c.post("/v1/admin/credits", headers=admin, json=grant)

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: post(), range(2)))
        assert [r.status_code for r in result] == [200, 200]
        assert (
            c.post(
                "/v1/admin/credits", headers=admin, json={**grant, "amount": 101}
            ).status_code
            == 409
        )
        plan = dict(
            email=target["email"],
            plan="creator",
            days=30,
            credits=25,
            reason="Gift only, no charge",
            idempotency_key="wallet-plan-123",
        )
        assert c.post("/v1/admin/plans", headers=admin, json=plan).status_code == 200
        assert c.post("/v1/admin/plans", headers=admin, json=plan).status_code == 200
        assert c.get("/v1/me", headers=ordinary).json()["balance"] == 125
    wipe_local()
    with TestClient(app) as c:
        me = c.get("/v1/me", headers=ordinary).json()
        assert (me["balance"], me["reserved"], me["plan"]) == (125, 0, "creator")
        wallet = c.get("/v1/wallet", headers=ordinary).json()
        assert wallet["balance"] == 125 and sorted(
            x["amount"] for x in wallet["transactions"]
        ) == [25, 100]
        assert c.get("/v1/wallet", headers=admin).json()["transactions"] == []
        directory = c.get("/v1/admin/users?search=recipient", headers=admin).json()[
            "users"
        ]
        assert directory[0]["balance"] == 125 and directory[0]["plan"] == "creator"
        assert (
            c.get("/v1/admin/overview", headers=admin).json()["durable_finances"]
            is True
        )
        assert len(c.get("/v1/me/export", headers=ordinary).json()["ledger"]) == 2


def test_independent_concurrent_grants_do_not_lose_updates(remote):
    with TestClient(app) as c:
        _, admin, target, ordinary = setup(c)

        def add(index):
            return c.post(
                "/v1/admin/credits",
                headers=admin,
                json=dict(
                    email=target["email"],
                    amount=10,
                    idempotency_key=f"parallel-grant-{index}",
                ),
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(add, range(4)))
        assert all(r.status_code == 200 for r in results)
        assert c.get("/v1/wallet", headers=ordinary).json()["balance"] == 40


def test_wallet_outage_fails_closed_and_plan_expiration(remote):
    with TestClient(app) as c:
        _, admin, target, ordinary = setup(c)
        body = dict(
            email=target["email"],
            plan="pro",
            days=1,
            credits=0,
            reason="Access gift",
            idempotency_key="expire-plan-123",
        )
        assert c.post("/v1/admin/plans", headers=admin, json=body).status_code == 200
        found = accounts.read("wallets", target["id"])
        data, version = found
        data["plan_expires_at"] = now() - timedelta(seconds=1)
        accounts.commit(
            [accounts.update_write("wallets", target["id"], data, version=version)]
        )
        assert c.get("/v1/me", headers=ordinary).json()["plan"] == "free"
        assert (
            c.post(
                "/v1/admin/plans",
                headers=admin,
                json={**body, "plan": "free", "credits": 1},
            ).status_code
            == 400
        )
        remote.unavailable = True
        assert c.get("/v1/wallet", headers=ordinary).status_code == 503
        assert (
            c.post(
                "/v1/admin/credits",
                headers=admin,
                json=dict(
                    email=target["email"], amount=5, idempotency_key="outage-grant-123"
                ),
            ).status_code
            == 503
        )


def test_generation_never_changes_roles_and_uses_actual_job_route(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=0)
    calls = []
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *args: (
            calls.append(args) or (b"Explicit local fixture output", "text/plain")
        ),
    )
    with TestClient(app) as c:
        user, ordinary = register(c)
        result = c.post("/v1/jobs", headers=ordinary, json=job_request(credits=0))
        assert result.status_code == 202 and result.json()["status"] == "queued"
        assert accounts.get(user["id"])["role"] == "user"
        assert c.get("/v1/admin/overview", headers=ordinary).status_code == 403
        assert worker.run_once()
        assert len(calls) == 1
        assert wallets.snapshot(user["id"])["balance"] == 0


def test_paid_generation_stays_gated_until_job_billing_is_durable(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *args: (_ for _ in ()).throw(AssertionError("No provider call allowed")),
    )
    with TestClient(app) as c:
        _, admin, target, ordinary = setup(c)
        assert (
            c.post(
                "/v1/admin/credits",
                headers=admin,
                json=dict(
                    email=target["email"], amount=20, idempotency_key="fund-user-123"
                ),
            ).status_code
            == 200
        )
        result = c.post("/v1/jobs", headers=ordinary, json=job_request(credits=5))
        assert (
            result.status_code == 409
            and result.json()["detail"] == "DURABLE_JOB_BILLING_REQUIRED"
        )
        assert c.get("/v1/me", headers=ordinary).json()["balance"] == 20
        with Session() as db:
            assert db.query(Job).count() == 0
