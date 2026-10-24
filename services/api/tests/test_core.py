import io
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from sqlalchemy import select
from .conftest import register
from haytile.db import Session, User, Model, Job, Ledger, Asset
from haytile import providers, storage
from haytile.worker import run_once


def configure(monkeypatch, studio="text", credits=4):
    monkeypatch.setenv("HAYTILE_GEMINI_API_KEY", "fixture-not-a-real-key")
    with Session.begin() as db:
        db.add(
            Model(
                studio=studio,
                model_id="test-fixture",
                enabled=True,
                credits=credits,
                price_source="https://example.test/pricing",
            )
        )


def job_request(
    studio="text", credits=4, key="test-key-0001", prompt="Write a test story"
):
    return {
        "studio": studio,
        "title": "A story",
        "prompt": prompt,
        "idempotency_key": key,
        "params": {},
        "confirmed_credits": credits,
    }


def fund(user_id, credits):
    with Session.begin() as db:
        db.get(User, user_id).balance = credits


def test_auth_persistence_and_logout(client):
    user, h = register(client)
    assert client.get("/v1/me", headers=h).json()["email"] == user["email"]
    r = client.post(
        "/v1/auth/login",
        json={"email": user["email"], "password": "wrong"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 401
    assert client.post("/v1/auth/logout", headers=h).status_code == 200
    assert client.get("/v1/me", headers=h).status_code == 401


def test_unauthenticated_and_admin_authorization(client):
    assert client.get("/v1/assets").status_code == 401
    _, h = register(client)
    assert client.get("/v1/admin/overview", headers=h).status_code == 403


def test_cookie_csrf_rejected(client):
    register(client)
    assert (
        client.post(
            "/v1/assets/text",
            json={"title": "CSRF", "text": "Bad"},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/assets/text",
            json={"title": "CSRF", "text": "Good"},
            headers={"Origin": "http://localhost:3000"},
        ).status_code
        == 201
    )


def test_library_lifecycle_and_private_download(client):
    _, a = register(client)
    asset = client.post(
        "/v1/assets/text",
        json={"title": "Original", "text": "Pawòl mwen\nEgzakteman."},
        headers=a,
    ).json()
    _, b = register(client, "other@example.test")
    assert client.get("/v1/assets", headers=b).json() == []
    assert (
        client.get("/v1/assets/" + asset["id"] + "/link", headers=b).status_code == 404
    )
    assert (
        client.patch(
            "/v1/assets/" + asset["id"], json={"title": "Stolen"}, headers=b
        ).status_code
        == 404
    )
    assert client.delete("/v1/assets/" + asset["id"], headers=b).status_code == 404
    assert (
        client.patch(
            "/v1/assets/" + asset["id"], json={"title": "New name"}, headers=a
        ).json()["title"]
        == "New name"
    )
    link = client.get("/v1/assets/" + asset["id"] + "/link", headers=a).json()["path"]
    assert client.get(link).text == "Pawòl mwen\nEgzakteman."
    assert client.get(link.replace("signature=", "signature=x")).status_code == 403
    assert client.delete("/v1/assets/" + asset["id"], headers=a).status_code == 200
    assert client.get(link).status_code == 404


def test_upload_checks_content_and_download_bytes(client):
    _, h = register(client)
    assert (
        client.post(
            "/v1/assets/upload",
            files={"file": ("bad.png", b"<script>alert(1)</script>", "image/png")},
            headers=h,
        ).status_code
        == 400
    )
    buff = io.BytesIO()
    Image.new("RGB", (20, 20), "blue").save(buff, "PNG")
    result = client.post(
        "/v1/assets/upload",
        files={"file": ("image.png", buff.getvalue(), "image/png")},
        headers=h,
    )
    assert result.status_code == 201
    link = client.get("/v1/assets/" + result.json()["id"] + "/link", headers=h).json()[
        "path"
    ]
    assert client.get(link).content == buff.getvalue()
    assert (
        client.post(
            "/v1/assets/upload",
            files={"file": ("script.svg", b"<svg/>", "image/svg+xml")},
            headers=h,
        ).status_code
        == 400
    )


def test_generation_requires_provider_no_fake_result(client):
    _, h = register(client)
    assert client.post("/v1/jobs", json=job_request(), headers=h).status_code == 503
    assert client.get("/v1/jobs", headers=h).json() == []


def test_successful_worker_persists_and_debits_once(client, monkeypatch):
    configure(monkeypatch)
    user, h = register(client)
    fund(user["id"], 10)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda *args: (b"Generated fixture content", "text/plain"),
    )
    first = client.post("/v1/jobs", json=job_request(), headers=h)
    assert first.status_code == 202, first.text
    duplicate = client.post("/v1/jobs", json=job_request(), headers=h)
    assert first.json()["id"] == duplicate.json()["id"]
    assert client.get("/v1/wallet", headers=h).json()["reserved"] == 4
    assert run_once() is True
    assert run_once() is False
    wallet = client.get("/v1/wallet", headers=h).json()
    assert wallet["balance"] == 6 and wallet["reserved"] == 0
    assert len([x for x in wallet["transactions"] if x["kind"] == "debit"]) == 1
    assert client.get("/v1/jobs", headers=h).json()[0]["status"] == "completed"
    assert (
        client.get("/v1/assets", headers=h).json()[0]["text"]
        == "Generated fixture content"
    )


def test_failed_job_releases_and_retry_no_double_charge(client, monkeypatch):
    configure(monkeypatch)
    user, h = register(client)
    fund(user["id"], 10)

    def fail(*_):
        raise providers.ProviderError("PROVIDER_HTTP_429")

    monkeypatch.setattr(providers, "generate", fail)
    job = client.post("/v1/jobs", json=job_request(), headers=h).json()
    run_once()
    wallet = client.get("/v1/wallet", headers=h).json()
    assert wallet["balance"] == 10 and wallet["reserved"] == 0
    assert client.get("/v1/assets", headers=h).json() == []
    assert client.post("/v1/jobs/" + job["id"] + "/retry", headers=h).status_code == 200
    monkeypatch.setattr(
        providers, "generate", lambda *_: (b"Retry result", "text/plain")
    )
    run_once()
    wallet = client.get("/v1/wallet", headers=h).json()
    assert wallet["balance"] == 6 and wallet["reserved"] == 0
    assert len([x for x in wallet["transactions"] if x["kind"] == "debit"]) == 1


def test_image_is_free_even_if_database_has_price(client, monkeypatch):
    configure(monkeypatch, "image", 999)
    _, h = register(client)
    buff = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buff, "PNG")
    monkeypatch.setattr(
        providers, "generate", lambda *_: (buff.getvalue(), "image/png")
    )
    assert (
        client.post("/v1/jobs", json=job_request("image", 0), headers=h).status_code
        == 202
    )
    run_once()
    wallet = client.get("/v1/wallet", headers=h).json()
    assert (
        wallet["balance"] == 0
        and wallet["reserved"] == 0
        and wallet["transactions"] == []
    )
    assert client.get("/v1/assets", headers=h).json()[0]["mime"] == "image/png"


def test_price_confirmation_and_idempotency_conflict(client, monkeypatch):
    configure(monkeypatch)
    user, h = register(client)
    fund(user["id"], 20)
    assert (
        client.post("/v1/jobs", json=job_request(credits=0), headers=h).status_code
        == 409
    )
    assert client.post("/v1/jobs", json=job_request(), headers=h).status_code == 202
    assert (
        client.post(
            "/v1/jobs", json=job_request(prompt="Changed prompt"), headers=h
        ).status_code
        == 409
    )


def test_atomic_reservations_prevent_overspend(client, monkeypatch):
    configure(monkeypatch)
    user, h = register(client)
    fund(user["id"], 4)

    def submit(i):
        return client.post(
            "/v1/jobs", json=job_request(key=f"concurrent-{i}"), headers=h
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(submit, range(2)))
    assert sorted(codes) == [202, 402]
    assert client.get("/v1/wallet", headers=h).json()["reserved"] == 4


def test_profile_export_and_account_deletion(client):
    user, h = register(client)
    assert (
        client.patch(
            "/v1/me", json={"name": "Nouvo", "locale": "fr"}, headers=h
        ).json()["locale"]
        == "fr"
    )
    asset = client.post(
        "/v1/assets/text", json={"title": "Private", "text": "Mine"}, headers=h
    ).json()
    link = client.get("/v1/assets/" + asset["id"] + "/link", headers=h).json()["path"]
    data = client.get("/v1/me/export", headers=h).json()
    assert data["assets"][0]["text"] == "Mine"
    assert "password" not in data["profile"]
    assert (
        client.request(
            "DELETE", "/v1/me", json={"password": "Wrong"}, headers=h
        ).status_code
        == 401
    )
    assert (
        client.request(
            "DELETE", "/v1/me", json={"password": "Long-test-password-123"}, headers=h
        ).status_code
        == 200
    )
    assert client.get("/v1/me", headers=h).status_code == 401
    assert client.get(link).status_code == 404


def test_admin_credit_grant_is_idempotent(client):
    user, h = register(client)
    with Session.begin() as db:
        db.get(User, user["id"]).role = "admin"
    payload = {
        "email": user["email"],
        "amount": 50,
        "idempotency_key": "grant-unique-test",
    }
    for _ in range(2):
        assert (
            client.post("/v1/admin/credits", json=payload, headers=h).status_code == 200
        )
    assert client.get("/v1/wallet", headers=h).json()["balance"] == 50
    assert (
        client.get("/v1/admin/overview", headers=h).json()["audit"][0]["action"]
        == "credits.grant"
    )


def test_admin_cannot_charge_basic_images(client):
    user, h = register(client)
    with Session.begin() as db:
        db.get(User, user["id"]).role = "admin"
    body = {
        "studio": "image",
        "model_id": "fixture",
        "enabled": False,
        "credits": 1,
        "price_source": "https://example.test",
        "operator_billing_ack": True,
    }
    assert client.put("/v1/admin/models", json=body, headers=h).status_code == 400


def test_reference_must_belong_to_owner(client, monkeypatch):
    configure(monkeypatch, "image", 0)
    _, a = register(client)
    asset = client.post(
        "/v1/assets/text", json={"title": "Not image", "text": "x"}, headers=a
    ).json()
    _, b = register(client, "other@example.test")
    body = job_request("image", 0)
    body["params"] = {"reference_asset_id": asset["id"]}
    assert client.post("/v1/jobs", json=body, headers=b).status_code == 400


def test_free_image_capacity_limit(client, monkeypatch):
    configure(monkeypatch, "image", 0)
    monkeypatch.setenv("HAYTILE_FREE_IMAGES_PER_DAY", "1")
    _, h = register(client)
    assert (
        client.post("/v1/jobs", json=job_request("image", 0), headers=h).status_code
        == 202
    )
    assert (
        client.post(
            "/v1/jobs", json=job_request("image", 0, key="different-key"), headers=h
        ).status_code
        == 429
    )
