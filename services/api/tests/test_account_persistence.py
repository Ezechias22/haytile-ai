"""Remote account authority survives total loss of the local SQL identity cache."""

import copy
import threading
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from haytile import accounts
from haytile.db import Base, Session, User, now
from haytile.main import app
from haytile.security import hash_token, password_hash

from .conftest import register


class FirestoreFixture:
    """Atomic REST document/precondition fixture, independent of SQL persistence."""

    def __init__(self):
        self.documents = {}
        self.version = 0
        self.lock = threading.Lock()
        self.unavailable = False

    def __call__(self, method, url, **kwargs):
        if self.unavailable:
            return httpx.Response(503)
        with self.lock:
            if method == "GET":
                key = url.split("/v1/", 1)[1]
                return (
                    httpx.Response(200, json=copy.deepcopy(self.documents[key]))
                    if key in self.documents
                    else httpx.Response(404)
                )
            body = kwargs["json"]
            if url.endswith("documents:commit"):
                for write in body["writes"]:
                    key = write.get("update", {}).get("name") or write["delete"]
                    old = self.documents.get(key)
                    pre = write.get("currentDocument", {})
                    if (
                        pre.get("exists") is False
                        and old
                        or "updateTime" in pre
                        and (not old or pre["updateTime"] != old["updateTime"])
                    ):
                        return httpx.Response(
                            409, json={"error": {"status": "FAILED_PRECONDITION"}}
                        )
                for write in body["writes"]:
                    key = write.get("update", {}).get("name") or write["delete"]
                    if "delete" in write:
                        self.documents.pop(key, None)
                    else:
                        self.version += 1
                        self.documents[key] = {
                            **copy.deepcopy(write["update"]),
                            "updateTime": str(self.version),
                        }
                return httpx.Response(200, json={})
            aggregate = url.endswith("documents:runAggregationQuery")
            query = (
                body["structuredAggregationQuery"]["structuredQuery"]
                if aggregate
                else body["structuredQuery"]
            )
            collection = query["from"][0]["collectionId"]
            rows = [
                copy.deepcopy(v)
                for k, v in self.documents.items()
                if "/documents/" + collection + "/" in k
            ]
            where = query.get("where")
            if where:
                filters = where.get("compositeFilter", {}).get("filters", [where])
                for item in filters:
                    f = item["fieldFilter"]
                    field = f["field"]["fieldPath"]
                    value = f["value"]["stringValue"]
                    op = f["op"]
                    rows = [
                        r
                        for r in rows
                        if field in r["fields"]
                        and {
                            "GREATER_THAN_OR_EQUAL": lambda x: x >= value,
                            "GREATER_THAN": lambda x: x > value,
                            "LESS_THAN": lambda x: x < value,
                            "EQUAL": lambda x: x == value,
                        }[op](r["fields"][field]["stringValue"])
                    ]
            if aggregate:
                return httpx.Response(
                    200,
                    json=[
                        {
                            "result": {
                                "aggregateFields": {
                                    "total": {"integerValue": str(len(rows))}
                                }
                            }
                        }
                    ],
                )
            for order in query.get("orderBy", []):
                field = order["field"]["fieldPath"]
                rows.sort(
                    key=lambda r: next(iter(r["fields"][field].values())),
                    reverse=order["direction"] == "DESCENDING",
                )
            offset = query.get("offset", 0)
            return httpx.Response(
                200,
                json=[
                    {"document": r}
                    for r in rows[offset : offset + query.get("limit", 10000)]
                ],
            )


@pytest.fixture
def remote(monkeypatch):
    fake = FirestoreFixture()
    monkeypatch.setenv("HAYTILE_ACCOUNT_PROVIDER", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("FIREBASE_DATABASE_ID", "default")
    monkeypatch.setattr(accounts.transport, "request", fake)
    return fake


def wipe_local():
    from haytile import records

    records._cursors.clear()
    with Session.begin() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))


def test_account_profile_role_and_session_survive_local_database_loss(
    remote, monkeypatch
):
    monkeypatch.setenv("HAYTILE_ADMIN_EMAIL", "creator@example.test")
    monkeypatch.setenv(
        "HAYTILE_ADMIN_ACTIVATION_CODE",
        "private-owner-fixture-code-at-least-32-characters",
    )
    with TestClient(app) as client:
        user, headers = register(client)
        assert (
            client.patch(
                "/v1/me", headers=headers, json={"name": "Durable name", "locale": "fr"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/v1/admin/activate",
                headers=headers,
                json={"code": "private-owner-fixture-code-at-least-32-characters"},
            ).status_code
            == 200
        )
    wipe_local()
    # New API instance + empty SQL, same independent remote documents and bearer token.
    with TestClient(app) as client:
        restored = client.get("/v1/me", headers=headers)
        assert restored.status_code == 200
        data = restored.json()
        assert (data["id"], data["name"], data["locale"], data["role"]) == (
            user["id"],
            "Durable name",
            "fr",
            "admin",
        )
        assert client.get("/v1/admin/users", headers=headers).json()["total"] == 1
        login = client.post(
            "/v1/auth/login",
            json={"email": user["email"], "password": "Long-test-password-123"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert login.status_code == 200 and login.json()["user"]["id"] == user["id"]
        assert (
            client.post(
                "/v1/auth/register",
                json={
                    "email": user["email"],
                    "password": "Other-long-password-123",
                    "name": "Duplicate",
                    "locale": "ht",
                },
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 409
        )
        assert client.post("/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/v1/me", headers=headers).status_code == 401
        assert (
            client.get(
                "/v1/me", headers={"Authorization": "Bearer " + login.json()["token"]}
            ).status_code
            == 200
        )


def test_outage_fails_closed_even_with_local_user_cache(remote):
    with TestClient(app) as client:
        user, headers = register(client)
        remote.unavailable = True
        assert client.get("/v1/me", headers=headers).status_code == 503
        assert (
            client.post(
                "/v1/auth/login",
                json={"email": user["email"], "password": "Long-test-password-123"},
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/v1/auth/register",
                json={
                    "email": "new@example.test",
                    "password": "Other-long-password-123",
                    "name": "New",
                    "locale": "ht",
                },
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 503
        )
        remote.unavailable = False
        assert client.get("/v1/me", headers=headers).status_code == 200


def test_reset_revokes_sessions_and_cannot_replay_or_mint_with_old_epoch(remote):
    with TestClient(app) as client:
        user, headers = register(client)
        old = accounts.by_email(user["email"])
        raw = "reset-fixture-long-enough-1234567890"
        accounts.issue_reset(old, hash_token(raw))
        wipe_local()
        body = {"token": raw, "password": "Replacement-long-password-123"}
        assert (
            client.post(
                "/v1/auth/password-reset/confirm",
                json=body,
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 200
        )
        assert client.get("/v1/me", headers=headers).status_code == 401
        assert (
            client.post(
                "/v1/auth/password-reset/confirm",
                json=body,
                headers={"Origin": "http://localhost:3000"},
            ).status_code
            == 400
        )
        assert (
            accounts.session(
                old, hash_token("new-session-fixture"), now() + timedelta(minutes=5)
            )
            is False
        )
        login = client.post(
            "/v1/auth/login",
            json={"email": user["email"], "password": body["password"]},
            headers={"Origin": "http://localhost:3000"},
        )
        assert login.status_code == 200


def test_deletion_cannot_resurrect_account_after_restart(remote):
    with TestClient(app) as client:
        user, headers = register(client)
        assert (
            client.request(
                "DELETE",
                "/v1/me",
                headers=headers,
                json={"password": "Long-test-password-123"},
            ).status_code
            == 200
        )
    wipe_local()
    with TestClient(app) as client:
        assert client.get("/v1/me", headers=headers).status_code == 401
        assert accounts.by_email(user["email"]) is None
        replacement, new_headers = register(client)
        assert replacement["id"] != user["id"]
        assert client.get("/v1/me", headers=headers).status_code == 401
        assert client.get("/v1/me", headers=new_headers).status_code == 200


def test_import_preserves_existing_id_password_and_role(remote, monkeypatch):
    monkeypatch.setenv("HAYTILE_ACCOUNT_IMPORT_LOCAL", "1")
    with Session.begin() as db:
        original = User(
            email="existing@example.test",
            password=password_hash("Existing-local-password-123"),
            name="Existing",
            locale="ht",
            role="admin",
        )
        db.add(original)
        db.flush()
        original_id = original.id
    with TestClient(app) as client:
        result = client.post(
            "/v1/auth/login",
            json={"email": original.email, "password": "Existing-local-password-123"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert result.status_code == 200 and result.json()["user"]["id"] == original_id
    wipe_local()
    assert accounts.by_email(original.email)["role"] == "admin"


def test_atomic_duplicate_email_registration_and_expired_session(remote):
    from concurrent.futures import ThreadPoolExecutor

    def create():
        try:
            return accounts.create(
                "duplicate@example.test",
                password_hash("Duplicate-password-123"),
                "Duplicate",
                "ht",
            )["id"]
        except accounts.DuplicateEmail:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert results.count("conflict") == 1
    account = accounts.by_email("duplicate@example.test")
    digest = hash_token("expired-session-fixture")
    assert accounts.session(account, digest, now() - timedelta(seconds=1))
    assert accounts.resolve(digest) is None


def test_deleted_remote_identity_is_not_reimported_from_stale_sql_cache(remote):
    with TestClient(app) as client:
        user, headers = register(client)
        accounts.remove(user["id"])
        # Simulate a crash before SQL cache cleanup completes.
        accounts.migrate_local()
        assert accounts.by_email(user["email"]) is None
        assert client.get("/v1/me", headers=headers).status_code == 401
