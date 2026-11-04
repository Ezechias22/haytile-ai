import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from haytile import accounts, billing, wallets
from haytile.db import now

from .conftest import register
from .test_account_persistence import FirestoreFixture, wipe_local


class StripeFixture:
    def __init__(self):
        self.calls = []
        self.sessions = {}
        self.customers = {}
        self.subscriptions = {}
        self.intents = {}

    def __call__(self, method, path, data=None, key=None, params=None):
        self.calls.append((method, path, data, key, params))
        if path.startswith("/prices/"):
            recurring = "recurring" in path
            return {
                "id": path.split("/")[-1],
                "active": True,
                "livemode": billing.live(),
                "currency": "usd",
                "unit_amount": 1000 if recurring else 500,
                "product": {"name": "Haytile Creator" if recurring else "Haytile 500 credits"},
                "recurring": {"interval": "month", "interval_count": 1} if recurring else None,
            }
        if path == "/customers":
            row = {"id": "cus_" + key[-16:], "deleted": False}
            self.customers[row["id"]] = row
            return row
        if path.startswith("/customers/"):
            cid = path.split("/")[-1]
            if method == "DELETE":
                self.customers[cid]["deleted"] = True
            return self.customers[cid]
        if path == "/subscriptions":
            return {"data": list(self.subscriptions.values())}
        if path.startswith("/subscriptions/"):
            return self.subscriptions[path.split("/")[-1]]
        if path == "/checkout/sessions":
            if key not in self.sessions:
                sid = "cs_fixture_" + str(len(self.sessions))
                row = {
                    "id": sid,
                    "url": "https://checkout.stripe.com/c/" + sid,
                    "mode": data["mode"],
                    "customer": data["customer"],
                    "client_reference_id": data["client_reference_id"],
                    "metadata": {"haytile_purchase_id": data["metadata[haytile_purchase_id]"]},
                    "payment_status": "paid",
                    "currency": "usd",
                    "amount_total": 1000 if "recurring" in data["line_items[0][price]"] else 500,
                    "line_items": {
                        "data": [{"price": {"id": data["line_items[0][price]"]}, "quantity": 1}]
                    },
                }
                self.sessions[key] = row
            return self.sessions[key]
        if path.startswith("/checkout/sessions/"):
            return next(v for v in self.sessions.values() if v["id"] == path.split("/")[-1])
        if path == "/billing_portal/configurations":
            return {"id": "bpc_fixture"}
        if path == "/billing_portal/sessions":
            return {"url": "https://billing.stripe.com/p/session/fixture"}
        if path.startswith("/payment_intents/"):
            return self.intents[path.split("/")[-1]]
        raise AssertionError("Unexpected Stripe operation " + method + " " + path)


@pytest.fixture
def setup_billing(client, monkeypatch):
    remote = FirestoreFixture()
    monkeypatch.setenv("HAYTILE_PUBLIC_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("HAYTILE_ACCOUNT_PROVIDER", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("FIREBASE_DATABASE_ID", "default")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_offline_fixture")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_offline_fixture")
    monkeypatch.setenv("HAYTILE_STRIPE_LIVE_ENABLED", "1")
    monkeypatch.setattr(accounts.transport, "request", remote)
    fake = StripeFixture()
    monkeypatch.setattr(billing, "stripe", fake)
    owner, admin = register(client, "stripe-owner@example.test")
    accounts.change(owner["id"], {"role": "admin"})
    user, auth = register(client, "stripe-buyer@example.test")
    client.cookies.clear()
    return owner, admin, user, auth, fake, remote


def offer(client, admin, recurring=False):
    body = {
        "id": "creator-monthly" if recurring else "credits-500",
        "price_id": "price_recurringfixture" if recurring else "price_fixturecredits",
        "credits": 1000 if recurring else 500,
        "plan": "creator" if recurring else "free",
    }
    result = client.post("/v1/admin/billing/offers", headers=admin, json=body)
    assert result.status_code == 200, result.text
    return body


def checkout(client, auth, offer_id):
    body = {"offer_id": offer_id, "idempotency_key": str(uuid.uuid4())}
    result = client.post("/v1/billing/checkout", headers=auth, json=body)
    assert result.status_code == 200, result.text
    return body, result


def event(kind, obj, mode=True, event_id=None):
    return {
        "id": event_id or "evt_" + uuid.uuid4().hex,
        "type": kind,
        "livemode": mode,
        "data": {"object": obj},
    }


def send(client, data, stamp=None, signature=None):
    raw = json.dumps(data, separators=(",", ":")).encode()
    stamp = str(stamp or int(time.time()))
    signed = hmac.new(
        b"whsec_offline_fixture", stamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/v1/billing/webhook",
        content=raw,
        headers={
            "content-type": "application/json",
            "stripe-signature": signature or "t=" + stamp + ",v1=" + signed,
        },
    )


def test_checkout_uses_approved_price_customer_and_idempotency_without_grant(client, setup_billing):
    owner, admin, user, auth, fake, remote = setup_billing
    selected = offer(client, admin)
    assert client.post("/v1/admin/billing/offers", headers=auth, json=selected).status_code == 403
    assert (
        client.post(
            "/v1/admin/billing/offers", headers=admin, json={**selected, "credits": 501}
        ).status_code
        == 409
    )
    body, response = checkout(client, auth, selected["id"])
    again = client.post("/v1/billing/checkout", headers=auth, json=body)
    assert again.json() == response.json()
    assert wallets.snapshot(user["id"])["balance"] == 0
    purchase = billing.query("billing_purchases")[0]
    assert purchase["user_id"] == user["id"] and purchase["credits"] == 500
    params = next(c[2] for c in fake.calls if c[1] == "/checkout/sessions")
    assert params["line_items[0][price]"] == "price_fixturecredits"
    assert params["line_items[0][quantity]"] == "1" and params["client_reference_id"] == user["id"]
    assert client.get("/v1/billing/catalog", headers=auth).json()["offers"][0]["unit_amount"] == 500
    assert (
        client.post(
            "/v1/billing/checkout", headers=auth, json={**body, "offer_id": "unknown-price"}
        ).status_code
        == 409
    )


def test_signed_paid_payment_grants_once_concurrently_and_survives_cache_loss(
    client, setup_billing
):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin)
    checkout(client, auth, selected["id"])
    obj = next(iter(fake.sessions.values()))
    events = [
        event("checkout.session.completed", obj),
        event("checkout.session.async_payment_succeeded", obj),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: send(client, events[i % 2]), range(4)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert wallets.snapshot(user["id"])["balance"] == 500
    wipe_local()
    assert client.get("/v1/wallet", headers=auth).json()["balance"] == 500
    assert len([e for e in wallets.history(user["id"]) if e["kind"] == "stripe_payment"]) == 1


def test_signatures_modes_and_unpaid_or_mismatched_sessions_never_grant(client, setup_billing):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin)
    checkout(client, auth, selected["id"])
    obj = next(iter(fake.sessions.values()))
    good = event("checkout.session.completed", obj)
    assert send(client, good, signature="t=1,v1=bad").status_code == 400
    assert send(client, good, stamp=int(time.time()) - 1000).status_code == 400
    assert send(client, {**good, "livemode": False}).status_code == 400
    assert (
        send(
            client, event("checkout.session.completed", {**obj, "payment_status": "unpaid"})
        ).status_code
        == 200
    )
    obj["amount_total"] = 1
    assert send(client, event("checkout.session.completed", obj)).status_code == 400
    assert wallets.snapshot(user["id"])["balance"] == 0


def test_sandbox_checkout_is_admin_only_and_cannot_fund_real_wallet(
    client, setup_billing, monkeypatch
):
    owner, admin, user, auth, fake, _ = setup_billing
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_offline_fixture")
    selected = offer(client, admin)
    assert not client.get("/v1/billing/catalog", headers=auth).json()["available"]
    assert (
        client.post(
            "/v1/billing/checkout",
            headers=auth,
            json={"offer_id": selected["id"], "idempotency_key": str(uuid.uuid4())},
        ).status_code
        == 503
    )
    checkout(client, admin, selected["id"])
    obj = next(iter(fake.sessions.values()))
    assert send(client, event("checkout.session.completed", obj, mode=False)).status_code == 200
    assert wallets.snapshot(owner["id"])["balance"] == 0
    assert accounts.read("billing_sandbox_wallets", owner["id"])[0]["balance"] == 500


def test_recurring_invoice_cycles_grant_once_cancel_and_do_not_regress(client, setup_billing):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin, True)
    checkout(client, auth, selected["id"])
    purchase = billing.query("billing_purchases")[0]
    sub = {
        "id": "sub_fixture",
        "customer": purchase["customer_id"],
        "status": "active",
        "created": int(time.time()),
        "metadata": {"haytile_purchase_id": purchase["id"]},
        "items": {"data": [{"quantity": 1, "price": {"id": selected["price_id"]}}]},
    }
    fake.subscriptions[sub["id"]] = sub
    end = int((now() + timedelta(days=30)).timestamp())
    invoice = {
        "id": "in_fixture1",
        "subscription": sub["id"],
        "customer": purchase["customer_id"],
        "billing_reason": "subscription_create",
        "status": "paid",
        "amount_paid": 1000,
        "currency": "usd",
        "lines": {"data": [{"period": {"end": end}}]},
    }
    assert send(client, event("invoice.paid", invoice)).status_code == 200
    assert send(client, event("invoice.paid", invoice)).status_code == 200
    assert (
        wallets.snapshot(user["id"])["balance"] == 1000
        and wallets.snapshot(user["id"])["plan"] == "creator"
    )
    invoice["id"] = "in_fixture2"
    invoice["billing_reason"] = "subscription_cycle"
    invoice["lines"]["data"][0]["period"]["end"] = end + 30 * 86400
    assert send(client, event("invoice.paid", invoice)).status_code == 200
    assert wallets.snapshot(user["id"])["balance"] == 2000
    assert (
        client.post(
            "/v1/billing/checkout",
            headers=auth,
            json={"offer_id": selected["id"], "idempotency_key": str(uuid.uuid4())},
        ).status_code
        == 409
    )
    fake.subscriptions[sub["id"]]["status"] = "canceled"
    assert (
        send(client, event("customer.subscription.deleted", {"id": sub["id"]})).status_code == 200
    )
    assert wallets.snapshot(user["id"])["plan"] == "free"
    assert wallets.snapshot(user["id"])["balance"] == 2000


def test_refund_hold_admin_resolution_portal_and_account_delete(client, setup_billing):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin)
    checkout(client, auth, selected["id"])
    obj = next(iter(fake.sessions.values()))
    assert send(client, event("checkout.session.completed", obj)).status_code == 200
    fake.intents["pi_fixture"] = {"metadata": obj["metadata"]}
    assert (
        send(
            client, event("charge.refunded", {"id": "ch_fixture", "payment_intent": "pi_fixture"})
        ).status_code
        == 200
    )
    assert wallets.snapshot(user["id"])["billing_hold"] == 1
    risk = billing.query("billing_risks")[0]
    assert (
        client.post(
            "/v1/admin/billing/risks/" + risk["id"] + "/resolve",
            headers=auth,
            json={"revoke_credits": 100, "reason": "Refund verified"},
        ).status_code
        == 403
    )
    for _ in range(2):
        r = client.post(
            "/v1/admin/billing/risks/" + risk["id"] + "/resolve",
            headers=admin,
            json={"revoke_credits": 100, "reason": "Refund verified in offline Stripe fixture"},
        )
        assert r.status_code == 200, r.text
    assert (
        wallets.snapshot(user["id"])["balance"] == 400
        and wallets.snapshot(user["id"])["billing_hold"] == 0
    )
    portal = client.post("/v1/billing/portal", headers=auth)
    assert portal.status_code == 200 and portal.json()["url"].startswith(
        "https://billing.stripe.com/"
    )
    configuration = next(c[2] for c in fake.calls if c[1] == "/billing_portal/configurations")
    assert configuration["features[subscription_update][enabled]"] == "false"
    result = client.request(
        "DELETE", "/v1/me", headers=auth, json={"password": "Long-test-password-123"}
    )
    assert result.status_code == 200, result.text
    assert next(iter(fake.customers.values()))["deleted"]


def test_live_checkout_gated_but_readonly_offer_setup_allowed(client, setup_billing, monkeypatch):
    _, admin, user, auth, _, _ = setup_billing
    monkeypatch.setenv("HAYTILE_STRIPE_LIVE_ENABLED", "0")
    selected = offer(client, admin)
    assert not client.get("/v1/billing/catalog", headers=auth).json()["available"]
    assert (
        client.post(
            "/v1/billing/checkout",
            headers=auth,
            json={"offer_id": selected["id"], "idempotency_key": str(uuid.uuid4())},
        ).status_code
        == 503
    )


def test_webhook_rejects_signed_malformed_payload(client, setup_billing):
    assert send(client, []).status_code == 400
    assert (
        send(
            client, {"id": "evt_bad", "livemode": True, "type": "invoice.paid", "data": []}
        ).status_code
        == 400
    )


def test_pending_subscription_reuses_checkout_and_blocks_another_plan(client, setup_billing):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin, True)
    _, first = checkout(client, auth, selected["id"])
    _, again = checkout(client, auth, selected["id"])
    assert first.json() == again.json() and len(fake.sessions) == 1
    changed = {**selected, "id": "pro-monthly", "plan": "pro"}
    assert client.post("/v1/admin/billing/offers", headers=admin, json=changed).status_code == 200
    blocked = client.post(
        "/v1/billing/checkout",
        headers=auth,
        json={"offer_id": changed["id"], "idempotency_key": str(uuid.uuid4())},
    )
    assert blocked.status_code == 409 and blocked.json()["detail"] == "SUBSCRIPTION_PENDING"


def test_stripe_rest_transport_uses_server_headers_and_safe_errors(monkeypatch):
    import httpx
    from fastapi import HTTPException

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_explicit_offline_fixture")
    captured = {}

    def request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return httpx.Response(200, json={"id": "cs_fixture"})

    monkeypatch.setattr(billing.httpx, "request", request)
    assert (
        billing.stripe("POST", "/checkout/sessions", data={"mode": "payment"}, key="dedup-fixture")[
            "id"
        ]
        == "cs_fixture"
    )
    assert captured["headers"]["Stripe-Version"] == billing.VERSION
    assert captured["headers"]["Authorization"] == "Bearer sk_test_explicit_offline_fixture"
    assert captured["headers"]["Idempotency-Key"] == "dedup-fixture"
    monkeypatch.setattr(
        billing.httpx,
        "request",
        lambda *a, **kw: httpx.Response(
            401, json={"error": {"message": "Do not expose provider internals"}}
        ),
    )
    with pytest.raises(HTTPException) as error:
        billing.stripe("GET", "/prices/price_fixture")
    assert error.value.detail == "STRIPE_REQUEST_FAILED"


def test_payment_receipt_is_owned_and_verified_only_after_signed_fulfillment(client, setup_billing):
    _, admin, user, auth, fake, _ = setup_billing
    selected = offer(client, admin)
    checkout(client, auth, selected["id"])
    purchase = billing.query("billing_purchases")[0]
    route = "/v1/billing/purchases/" + purchase["id"]
    assert client.get(route, headers=auth).json()["status"] == "pending"
    assert client.get(route, headers=admin).status_code == 404
    obj = next(iter(fake.sessions.values()))
    assert send(client, event("checkout.session.completed", obj)).status_code == 200
    for _ in range(2):
        assert client.get(route, headers=auth).json() == {
            "status": "paid",
            "test_mode": False,
            "credits": 500,
        }
    assert wallets.snapshot(user["id"])["balance"] == 500


def test_durable_reservation_rechecks_hold_after_admission_snapshot(
    client, setup_billing, monkeypatch
):
    from fastapi import HTTPException

    from haytile import live_voice

    _, admin, user, auth, _, _ = setup_billing
    wallets.grant(user["email"], 100, user["id"], "held-wallet-fixture")
    found = accounts.read("wallets", user["id"])
    accounts.commit(
        [
            accounts.update_write(
                "wallets", user["id"], {**found[0], "billing_hold": 1}, version=found[1]
            )
        ]
    )
    original = wallets.snapshot
    # Model the race: the admission snapshot predates a refund's durable hold.
    monkeypatch.setattr(wallets, "snapshot", lambda uid: {**original(uid), "billing_hold": 0})
    with pytest.raises(HTTPException) as error:
        live_voice.reserve(
            user["id"],
            live_voice.Start(
                voice_name="Puck", model_id=live_voice.MODEL, idempotency_key=str(uuid.uuid4())
            ),
        )
    assert error.value.detail == "BILLING_REVIEW_REQUIRED"
    bank = accounts.read("wallets", user["id"])[0]
    assert bank["balance"] == 100 and bank["reserved"] == 0 and bank["billing_hold"] == 1
