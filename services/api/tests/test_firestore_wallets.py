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
        assert c.post("/v1/admin/credits", headers=ordinary, json=grant).status_code == 403

        def post():
            return c.post("/v1/admin/credits", headers=admin, json=grant)

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: post(), range(2)))
        assert [r.status_code for r in result] == [200, 200]
        assert (
            c.post("/v1/admin/credits", headers=admin, json={**grant, "amount": 101}).status_code
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
        assert wallet["balance"] == 125 and sorted(x["amount"] for x in wallet["transactions"]) == [
            25,
            100,
        ]
        assert c.get("/v1/wallet", headers=admin).json()["transactions"] == []
        directory = c.get("/v1/admin/users?search=recipient", headers=admin).json()["users"]
        assert directory[0]["balance"] == 125 and directory[0]["plan"] == "creator"
        assert c.get("/v1/admin/overview", headers=admin).json()["durable_finances"] is True
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
        accounts.commit([accounts.update_write("wallets", target["id"], data, version=version)])
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
                json=dict(email=target["email"], amount=5, idempotency_key="outage-grant-123"),
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
        lambda *args: calls.append(args) or (b"Explicit local fixture output", "text/plain"),
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


def test_paid_generation_reserves_and_settles_durably(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *args: (b"Explicit paid-work fixture", "text/plain"),
    )
    with TestClient(app) as c:
        _, admin, target, ordinary = setup(c)
        assert (
            c.post(
                "/v1/admin/credits",
                headers=admin,
                json=dict(email=target["email"], amount=20, idempotency_key="fund-user-123"),
            ).status_code
            == 200
        )
        result = c.post("/v1/jobs", headers=ordinary, json=job_request(credits=5))
        assert result.status_code == 202, result.text
        assert c.get("/v1/wallet", headers=ordinary).json()["reserved"] == 5
        job_id = result.json()["id"]
        wipe_local()
        assert worker.run_once()
        assert c.get("/v1/me", headers=ordinary).json()["balance"] == 15
        wallet = c.get("/v1/wallet", headers=ordinary).json()
        assert wallet["reserved"] == 0
        assert len([e for e in wallet["transactions"] if e["kind"] == "debit"]) == 1
        wipe_local()
        jobs = c.get("/v1/jobs", headers=ordinary).json()
        assert jobs[0]["id"] == job_id and jobs[0]["status"] == "completed"
        assets = c.get("/v1/assets", headers=ordinary).json()
        assert assets[0]["text"] == "Explicit paid-work fixture"


def test_failure_releases_reservation_and_retry_debits_only_once(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    with TestClient(app) as c:
        _, admin, target, h = setup(c)
        c.post(
            "/v1/admin/credits",
            headers=admin,
            json=dict(email=target["email"], amount=10, idempotency_key="retry-fund-123"),
        )
        job = c.post("/v1/jobs", headers=h, json=job_request(credits=5)).json()
        monkeypatch.setattr(
            providers,
            "generate",
            lambda *a: (_ for _ in ()).throw(providers.ProviderError("PROVIDER_QUOTA_EXCEEDED")),
        )
        assert worker.run_once()
        bank = c.get("/v1/wallet", headers=h).json()
        assert bank["balance"] == 10 and bank["reserved"] == 0
        assert c.post("/v1/jobs/" + job["id"] + "/retry", headers=h).status_code == 200
        monkeypatch.setattr(
            providers,
            "generate",
            lambda *a: (b"Retry fixture, not a provider response", "text/plain"),
        )
        assert worker.run_once()
        assert not worker.run_once()
        bank = c.get("/v1/wallet", headers=h).json()
        assert bank["balance"] == 5 and bank["reserved"] == 0
        assert sum(e["kind"] == "debit" for e in bank["transactions"]) == 1


def test_ambiguous_completed_commit_recovers_without_deleting_the_published_file(
    remote, monkeypatch
):
    import httpx

    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    lost = [False]

    def transport(method, url, **kwargs):
        response = remote(method, url, **kwargs)
        writes = kwargs.get("json", {}).get("writes", [])
        if (
            not lost[0]
            and response.status_code == 200
            and any(
                "/documents/haytile_assets/" in w.get("update", {}).get("name", "") for w in writes
            )
        ):
            lost[0] = True
            return httpx.Response(503)
        return response

    monkeypatch.setattr(accounts.transport, "request", transport)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *a: (b"Published fixture survives a lost commit response", "text/plain"),
    )
    with TestClient(app) as c:
        _, admin, target, h = setup(c)
        c.post(
            "/v1/admin/credits",
            headers=admin,
            json=dict(email=target["email"], amount=10, idempotency_key="uncertain-fund-123"),
        )
        response = c.post("/v1/jobs", headers=h, json=job_request(credits=5))
        assert response.status_code == 202
        assert worker.run_once() and lost[0]
        wipe_local()
        job = c.get("/v1/jobs", headers=h).json()[0]
        assert job["status"] == "completed"
        asset = c.get("/v1/assets", headers=h).json()[0]
        link = c.get("/v1/assets/" + asset["id"] + "/link", headers=h).json()["path"]
        assert c.get(link).content == b"Published fixture survives a lost commit response"
        assert c.get("/v1/wallet", headers=h).json()["balance"] == 5


def test_durable_reservations_reject_overspend_before_any_provider_call(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *a: (_ for _ in ()).throw(AssertionError("No generation during admission")),
    )
    with TestClient(app) as c:
        _, admin, target, h = setup(c)
        c.post(
            "/v1/admin/credits",
            headers=admin,
            json=dict(email=target["email"], amount=6, idempotency_key="overspend-fund-123"),
        )

        def submit(i):
            return c.post(
                "/v1/jobs",
                headers=h,
                json=job_request(credits=5, key="concurrent-paid-" + str(i)),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(submit, range(2)))
        assert sorted(r.status_code for r in result) == [202, 402]
        assert c.get("/v1/wallet", headers=h).json()["reserved"] == 5


def test_replay_recovers_the_canonical_job_even_if_local_projection_misses_it(remote, monkeypatch):
    from sqlalchemy import delete

    from haytile import records

    monkeypatch.setenv("HAYTILE_GENERATION_ENABLED", "1")
    monkeypatch.setenv("HAYTILE_WORKER_ENABLED", "1")
    configure(monkeypatch, credits=5)
    with TestClient(app) as c:
        _, admin, target, h = setup(c)
        c.post(
            "/v1/admin/credits",
            headers=admin,
            json=dict(email=target["email"], amount=10, idempotency_key="replay-fund-123"),
        )
        body = job_request(credits=5)
        first = c.post("/v1/jobs", headers=h, json=body)
        assert first.status_code == 202
        with Session.begin() as db:
            db.execute(delete(Job))
        monkeypatch.setattr(records, "sync_user", lambda user_id: None)
        replay = c.post("/v1/jobs", headers=h, json=body)
        assert replay.status_code == 202 and replay.json()["id"] == first.json()["id"]
        assert wallets.snapshot(target["id"])["reserved"] == 5
        conflict = c.post("/v1/jobs", headers=h, json={**body, "prompt": "Different request"})
        assert conflict.status_code == 409


@pytest.mark.parametrize("response_lost_after_commit", [False, True])
def test_delete_only_commit_requires_tombstone_confirmation(
    remote, monkeypatch, response_lost_after_commit
):
    import httpx

    with TestClient(app) as c:
        _, h = register(c, "delete-confirm@example.test")
        project = c.post(
            "/v1/projects", headers=h, json={"title": "Delete safely", "document": {}}
        ).json()
        lost = [False]

        def transport(method, url, **kwargs):
            writes = kwargs.get("json", {}).get("writes", [])
            deleting = any(
                w.get("update", {}).get("fields", {}).get("deleted", {}).get("integerValue") == "1"
                for w in writes
            )
            if deleting and not lost[0]:
                lost[0] = True
                if response_lost_after_commit:
                    remote(method, url, **kwargs)
                return httpx.Response(503)
            return remote(method, url, **kwargs)

        monkeypatch.setattr(accounts.transport, "request", transport)
        deleted = c.delete("/v1/projects/" + project["id"], headers=h)
        assert lost[0]
        if response_lost_after_commit:
            assert deleted.status_code == 200
        else:
            assert deleted.status_code == 503
            assert c.get("/v1/projects", headers=h).json()[0]["id"] == project["id"]
            assert c.delete("/v1/projects/" + project["id"], headers=h).status_code == 200
        wipe_local()
        assert c.get("/v1/projects", headers=h).json() == []
