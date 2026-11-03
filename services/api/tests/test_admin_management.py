from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, func
from haytile.db import Session, User, Ledger, Audit, Membership, now
from .conftest import register


def administrator(client):
    owner, headers = register(client, "owner@example.test")
    with Session.begin() as db:
        db.get(User, owner["id"]).role = "admin"
    return owner, headers


def test_access_and_filtered_directory(client):
    assert client.get("/v1/admin/users").status_code == 401
    user, ordinary = register(client, "person@example.test")
    assert client.get("/v1/admin/users", headers=ordinary).status_code == 403
    assert (
        client.post(
            "/v1/admin/plans",
            headers=ordinary,
            json=dict(
                email=user["email"],
                plan="pro",
                days=30,
                credits=10,
                reason="Gift access",
                idempotency_key="assignment-123",
            ),
        ).status_code
        == 403
    )
    _, headers = administrator(client)
    result = client.get("/v1/admin/users?search=person", headers=headers).json()
    assert result["total"] == 1 and result["users"][0]["id"] == user["id"]
    assert "password" not in result["users"][0]
    assert client.get("/v1/admin/users?search=%25", headers=headers).json()["total"] == 0
    assert client.get("/v1/admin/users?offset=-1", headers=headers).status_code == 400


def test_plan_assignment_atomic_replay_conflict_and_expiration(client):
    _, headers = administrator(client)
    user, ordinary = register(client)
    body = dict(
        email=user["email"],
        plan="creator",
        days=30,
        credits=75,
        reason="Launch gift",
        idempotency_key="assignment-123",
    )

    def assign():
        return client.post("/v1/admin/plans", headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: assign(), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    me = client.get("/v1/me", headers=ordinary).json()
    assert me["balance"] == 75 and me["plan"] == "creator"
    assert (
        client.post("/v1/admin/plans", headers=headers, json={**body, "credits": 76}).status_code
        == 409
    )
    with Session.begin() as db:
        assert (
            db.scalar(select(func.count()).select_from(Ledger).where(Ledger.user_id == user["id"]))
            == 1
        )
        assert (
            db.scalar(select(func.count()).select_from(Audit).where(Audit.action == "plan.assign"))
            == 1
        )
        db.get(Membership, user["id"]).expires_at = now() - timedelta(seconds=1)
    assert client.get("/v1/me", headers=ordinary).json()["plan"] == "free"
    assert (
        client.post(
            "/v1/admin/plans",
            headers=headers,
            json={**body, "plan": "free", "idempotency_key": "other-key-123"},
        ).status_code
        == 400
    )


def test_credit_grant_replay_and_conflict(client):
    _, headers = administrator(client)
    user, ordinary = register(client)
    body = dict(email=user["email"], amount=20, idempotency_key="credit-12345")
    assert client.post("/v1/admin/credits", headers=headers, json=body).status_code == 200
    assert client.post("/v1/admin/credits", headers=headers, json=body).status_code == 200
    assert client.get("/v1/me", headers=ordinary).json()["balance"] == 20
    assert (
        client.post("/v1/admin/credits", headers=headers, json={**body, "amount": 21}).status_code
        == 409
    )


def test_financial_operations_block_temporary_database(client, monkeypatch):
    from haytile import main

    _, headers = administrator(client)
    monkeypatch.setattr(main.engine.dialect, "name", "sqlite")
    assert client.get("/v1/admin/overview", headers=headers).json()["durable_finances"] is False
    body = dict(
        email="none@example.test",
        plan="pro",
        days=30,
        credits=5,
        reason="Gift access",
        idempotency_key="assignment-123",
    )
    assert (
        client.post("/v1/admin/plans", headers=headers, json=body).json()["detail"]
        == "PERSISTENT_POSTGRES_REQUIRED"
    )
    assert (
        client.post(
            "/v1/admin/credits",
            headers=headers,
            json=dict(email="none@example.test", amount=5, idempotency_key="credit-12345"),
        ).status_code
        == 409
    )


def test_activation_requires_private_code_and_matching_account(client, monkeypatch):
    user, headers = register(client)
    monkeypatch.setenv("HAYTILE_ADMIN_EMAIL", user["email"])
    monkeypatch.setenv(
        "HAYTILE_ADMIN_ACTIVATION_CODE", "private-fixture-code-at-least-32-characters"
    )
    assert (
        client.post(
            "/v1/admin/activate",
            headers=headers,
            json={"code": "incorrect-code-at-least-32-characters"},
        ).status_code
        == 403
    )
    assert (
        client.post("/v1/admin/activate", headers=headers, json={"code": "é" * 40}).status_code
        == 403
    )
    _, other = register(client, "outsider@example.test")
    code = {"code": "private-fixture-code-at-least-32-characters"}
    assert client.post("/v1/admin/activate", headers=other, json=code).status_code == 403
    assert client.post("/v1/admin/activate", headers=headers, json=code).status_code == 200
    assert client.get("/v1/admin/users", headers=headers).status_code == 200
    assert client.post("/v1/admin/activate", headers=headers, json=code).status_code == 200
    with Session() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Audit).where(Audit.action == "admin.activate")
            )
            == 1
        )
