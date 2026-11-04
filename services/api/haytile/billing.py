"""Stripe-hosted web payments. Signed webhooks, never return URLs, grant credits.

Firestore is the authority. Sandbox wallets are isolated from spendable balances.
"""

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from . import accounts as store
from . import wallets
from .db import now
from .main import admin, current, fail, limit
from .security import hash_token

router = APIRouter()
VERSION = "2025-02-24.acacia"
API = "https://api.stripe.com/v1"
# App retail floors. BRL reference: USD/BRL 5.4654 (ECB/Frankfurter, 2026-11-04).
# One reference credit is USD 0.01; round BRL minor units upward. Not a live FX quote.
CREDIT_MIN_MINOR = {"usd": 1, "brl": 6}


def live():
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    return key.startswith(("sk_live_", "rk_live_"))


def key_present():
    return os.environ.get("STRIPE_SECRET_KEY", "").startswith(
        ("sk_test_", "sk_live_", "rk_test_", "rk_live_")
    )


def key_ready():
    return key_present() and (not live() or os.environ.get("HAYTILE_STRIPE_LIVE_ENABLED") == "1")


def ready():
    origin = urlparse(os.environ.get("HAYTILE_PUBLIC_ORIGIN", ""))
    valid_origin = bool(origin.netloc) and origin.scheme in ("http", "https")
    if os.environ.get("HAYTILE_ENV") == "production":
        valid_origin = valid_origin and origin.scheme == "https"
    return (
        store.enabled()
        and key_ready()
        and valid_origin
        and os.environ.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")
    )


def stripe(method, path, data=None, key=None, params=None):
    if not key_present():
        fail("BILLING_NOT_CONFIGURED", 503)
    headers = {
        "Authorization": "Bearer " + os.environ["STRIPE_SECRET_KEY"],
        "Stripe-Version": VERSION,
    }
    if key:
        headers["Idempotency-Key"] = key
    try:
        r = httpx.request(method, API + path, headers=headers, data=data, params=params, timeout=25)
        if r.status_code not in (200, 201):
            fail("STRIPE_REQUEST_FAILED", 503)
        return r.json()
    except (httpx.HTTPError, ValueError):
        fail("STRIPE_REQUEST_FAILED", 503)


def query(kind, field=None, value=None):
    q = {"from": [{"collectionId": "haytile_" + kind}], "limit": 100}
    if field:
        q["where"] = {
            "fieldFilter": {
                "field": {"fieldPath": field},
                "op": "EQUAL",
                "value": store.encode({"x": value})["x"],
            }
        }
    r = store.request("POST", "/documents:runQuery", json={"structuredQuery": q})
    if r.status_code != 200:
        raise store.Unavailable()
    return [store.decode(row["document"]) for row in r.json() if "document" in row]


def put(kind, key, data, found=None):
    return store.update_write(
        kind, key, data, version=found[1] if found else None, create=not bool(found)
    )


def offer(offer_id):
    found = store.read("billing_offers", offer_id)
    if not found or not found[0]["enabled"] or found[0]["livemode"] != int(live()):
        fail("OFFER_UNAVAILABLE", 409)
    return found[0]


class Offer(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,60}$")
    price_id: str = Field(pattern=r"^price_[a-zA-Z0-9]{5,70}$")
    credits: int = Field(ge=100, le=1000000)
    plan: str = Field(pattern=r"^(free|creator|pro)$")
    enabled: bool = True


@router.get("/v1/admin/billing")
def status(user=Depends(admin)):
    return {
        "key_configured": key_present(),
        "live_enabled": os.environ.get("HAYTILE_STRIPE_LIVE_ENABLED") == "1",
        "webhook_configured": bool(
            os.environ.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")
        ),
        "durable": store.enabled(),
        "live": live(),
        "ready": ready(),
        "offers": query("billing_offers") if store.enabled() else [],
        "risks": query("billing_risks", "resolved", 0) if store.enabled() else [],
        "sandbox_balance": (store.read("billing_sandbox_wallets", user.id) or [wallets.base()])[0][
            "balance"
        ]
        if store.enabled()
        else 0,
    }


@router.post("/v1/admin/billing/offers")
def save_offer(body: Offer, user=Depends(admin)):
    if not store.enabled():
        fail("PERSISTENT_POSTGRES_REQUIRED", 503)
    limit("stripe-offers:" + user.id, 30, 3600)
    price = stripe("GET", "/prices/" + body.price_id, params={"expand[]": "product"})
    recurring = price.get("recurring")
    if (
        not price.get("active")
        or price.get("livemode") != live()
        or price.get("currency") not in CREDIT_MIN_MINOR
        or type(price.get("unit_amount")) is not int
    ):
        fail("STRIPE_PRICE_UNSUPPORTED", 409)
    # 1 Haytile reference credit = 1 US cent. Do not permit below-reference offers.
    if price["unit_amount"] < max(body.credits, 100) * CREDIT_MIN_MINOR[price["currency"]]:
        fail("STRIPE_PRICE_TOO_LOW", 409)
    if recurring:
        if (
            body.plan == "free"
            or recurring.get("interval") not in ("month", "year")
            or recurring.get("interval_count") != 1
        ):
            fail("STRIPE_PRICE_UNSUPPORTED", 409)
    elif body.plan != "free":
        fail("STRIPE_PRICE_UNSUPPORTED", 409)
    product = price.get("product", {})
    label = product.get("name", body.id) if isinstance(product, dict) else body.id
    row = {
        "id": body.id,
        "price_id": body.price_id,
        "credits": body.credits,
        "plan": body.plan,
        "enabled": int(body.enabled),
        "mode": "subscription" if recurring else "payment",
        "interval": recurring["interval"] if recurring else "",
        "unit_amount": price["unit_amount"],
        "currency": price["currency"],
        "livemode": int(live()),
        "label": str(label)[:100],
        "actor_id": user.id,
        "updated_at": now(),
    }
    for _ in range(8):
        found = store.read("billing_offers", body.id)
        try:
            store.commit(
                [
                    put("billing_offers", body.id, row, found),
                    store.audit_write(user.id, "billing.offer", body.id),
                ]
            )
            return row
        except store.Conflict:
            continue
    raise store.Unavailable()


@router.get("/v1/billing/catalog")
def catalog(user=Depends(current)):
    allowed = ready() and (live() or user.role == "admin")
    rows = query("billing_offers", "enabled", 1) if allowed else []
    return {
        "available": allowed,
        "has_customer": bool(
            store.read("billing_customers", hash_token(user.id + ":" + str(live())))
        )
        if allowed
        else False,
        "test_mode": not live(),
        "sandbox_balance": (store.read("billing_sandbox_wallets", user.id) or [wallets.base()])[0][
            "balance"
        ]
        if allowed and not live()
        else 0,
        "offers": [
            {
                k: o[k]
                for k in [
                    "id",
                    "label",
                    "credits",
                    "plan",
                    "unit_amount",
                    "currency",
                    "mode",
                    "interval",
                ]
            }
            for o in rows
            if o["livemode"] == int(live())
        ],
    }


@router.get("/v1/billing/purchases/{purchase_id}")
def purchase_status(purchase_id: str, user=Depends(current)):
    if not store.enabled() or not re.fullmatch("[a-f0-9]{64}", purchase_id):
        fail("NOT_FOUND", 404)
    found = store.read("billing_purchases", purchase_id)
    if not found or found[0]["user_id"] != user.id:
        fail("NOT_FOUND", 404)
    row = found[0]
    return {
        "status": row.get("payment_status", "pending"),
        "test_mode": not bool(row["livemode"]),
        "credits": row["credits"],
    }


def customer(user):
    key = hash_token(user.id + ":" + str(live()))
    found = store.read("billing_customers", key)
    if found:
        return key, found
    data = stripe(
        "POST",
        "/customers",
        data={"email": user.email, "name": user.name, "metadata[haytile_user_id]": user.id},
        key="haytile-customer-" + key,
    )
    row = {
        "user_id": user.id,
        "customer_id": data["id"],
        "livemode": int(live()),
        "created_at": now(),
    }
    try:
        store.commit([put("billing_customers", key, row)])
    except store.Conflict:
        pass
    return key, store.read("billing_customers", key)


class Checkout(BaseModel):
    offer_id: str = Field(pattern=r"^[a-z0-9-]{3,60}$")
    idempotency_key: str = Field(min_length=16, max_length=80)


@router.post("/v1/billing/checkout")
def checkout(body: Checkout, user=Depends(current)):
    if not ready() or (not live() and user.role != "admin"):
        fail("BILLING_NOT_CONFIGURED", 503)
    limit("stripe-checkout:" + user.id, 10, 60)
    selected = offer(body.offer_id)
    ckey, account = customer(user)
    # Refuse a second recurring subscription; manage the existing one in the portal.
    if selected["mode"] == "subscription":
        subs = stripe(
            "GET",
            "/subscriptions",
            params={"customer": account[0]["customer_id"], "status": "all", "limit": 100},
        )
        if any(
            s["status"] in ("active", "trialing", "past_due", "unpaid", "incomplete", "paused")
            for s in subs.get("data", [])
        ):
            fail("SUBSCRIPTION_EXISTS", 409)
    pid = hash_token(user.id + ":" + str(live()) + ":" + body.idempotency_key)
    for _ in range(8):
        purchase = store.read("billing_purchases", pid)
        c = store.read("billing_customers", ckey)
        if purchase:
            if purchase[0]["user_id"] != user.id or purchase[0]["offer_id"] != body.offer_id:
                fail("IDEMPOTENCY_CONFLICT", 409)
            row = purchase[0]
            break
        row = {
            **selected,
            "id": pid,
            "offer_id": selected["id"],
            "user_id": user.id,
            "customer_id": c[0]["customer_id"],
            "created_at": now(),
        }
        writes = [put("billing_purchases", pid, row)]
        if row["mode"] == "subscription":
            pending = c[0].get("pending_purchase", "")
            if pending and pending != pid and c[0].get("pending_until", 0) > int(time.time()):
                prior = store.read("billing_purchases", pending)
                if prior and prior[0]["offer_id"] == body.offer_id:
                    pid = pending
                    row = prior[0]
                    break
                fail("SUBSCRIPTION_PENDING", 409)
            writes.append(
                put(
                    "billing_customers",
                    ckey,
                    {**c[0], "pending_purchase": pid, "pending_until": int(time.time()) + 3600},
                    c,
                )
            )
        try:
            store.commit(writes)
            break
        except store.Conflict:
            continue
    else:
        raise store.Unavailable()
    origin = os.environ["HAYTILE_PUBLIC_ORIGIN"].rstrip("/")
    data = {
        "mode": row["mode"],
        "adaptive_pricing[enabled]": "false",
        "customer": row["customer_id"],
        "client_reference_id": user.id,
        "line_items[0][price]": row["price_id"],
        "line_items[0][quantity]": "1",
        "success_url": origin + "/?billing=return&purchase_id=" + pid,
        "cancel_url": origin + "/?billing=cancel",
        "metadata[haytile_purchase_id]": pid,
    }
    if row["mode"] == "subscription":
        data["subscription_data[metadata][haytile_purchase_id]"] = pid
    else:
        data["payment_intent_data[metadata][haytile_purchase_id]"] = pid
    session = stripe("POST", "/checkout/sessions", data=data, key="haytile-checkout-" + pid)
    url = session.get("url", "")
    if urlparse(url).scheme != "https" or urlparse(url).netloc != "checkout.stripe.com":
        fail("STRIPE_REQUEST_FAILED", 503)
    return {"url": url, "test_mode": not live()}


@router.post("/v1/billing/portal")
def portal(user=Depends(current)):
    if not ready() or (not live() and user.role != "admin"):
        fail("BILLING_NOT_CONFIGURED", 503)
    limit("stripe-portal:" + user.id, 10, 3600)
    key = hash_token(user.id + ":" + str(live()))
    found = store.read("billing_customers", key)
    if not found:
        fail("NOT_FOUND", 404)
    configuration = stripe(
        "POST",
        "/billing_portal/configurations",
        data={
            "features[invoice_history][enabled]": "true",
            "features[payment_method_update][enabled]": "true",
            "features[subscription_cancel][enabled]": "true",
            "features[subscription_cancel][mode]": "at_period_end",
            "features[subscription_update][enabled]": "false",
        },
        key="haytile-portal-v1-" + str(live()),
    )
    result = stripe(
        "POST",
        "/billing_portal/sessions",
        data={
            "customer": found[0]["customer_id"],
            "configuration": configuration["id"],
            "return_url": os.environ["HAYTILE_PUBLIC_ORIGIN"].rstrip("/") + "/?billing=return",
        },
    )
    url = result.get("url", "")
    if urlparse(url).scheme != "https" or urlparse(url).netloc != "billing.stripe.com":
        fail("STRIPE_REQUEST_FAILED", 503)
    return {"url": url}


def signature(body, header):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret.startswith("whsec_"):
        return False
    try:
        parts = [part.split("=", 1) for part in header.split(",")]
        timestamp = next(value for name, value in parts if name == "t")
        if abs(time.time() - int(timestamp)) > 300:
            return False
        expected = hmac.new(
            secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        return any(name == "v1" and hmac.compare_digest(value, expected) for name, value in parts)
    except (ValueError, StopIteration):
        return False


def grant(event, purchase, cycle, period_end=0, subscription=None):
    event_key = hash_token(event["id"])
    cycle_key = hash_token(cycle)
    user_id = purchase["user_id"]
    sandbox = not event["livemode"]
    wallet_kind = "billing_sandbox_wallets" if sandbox else "wallets"
    for _ in range(8):
        previous = store.read("billing_events", event_key)
        if previous:
            return
        account = store.read("accounts", user_id)
        if not account or account[0].get("status") != "active":
            return
        duplicate = store.read("billing_cycles", cycle_key)
        marker = {
            "user_id": user_id,
            "kind": event["type"],
            "created_at": now(),
            "livemode": int(not sandbox),
        }
        writes = [
            put("billing_events", event_key, marker),
            put("accounts", user_id, account[0], account),
        ]
        if not duplicate:
            found = store.read(wallet_kind, user_id)
            bank = wallets.validate(found[0]) if found else wallets.base()
            if bank["balance"] + purchase["credits"] > 1000000000:
                raise store.Unavailable()
            bank["balance"] += purchase["credits"]
            bank["updated_at"] = now()
            if (
                subscription
                and subscription.get("status") in ("active", "trialing")
                and period_end > int(time.time())
            ):
                if subscription.get("created", 0) >= bank.get("stripe_subscription_created", 0):
                    bank.update(
                        plan=purchase["plan"],
                        plan_expires_at=datetime.fromtimestamp(period_end, timezone.utc),
                        stripe_subscription_id=subscription["id"],
                        stripe_subscription_created=subscription.get("created", 0),
                    )
            purchased = store.read("billing_purchases", purchase["id"])
            if purchased:
                writes.append(
                    put(
                        "billing_purchases",
                        purchase["id"],
                        {
                            **purchased[0],
                            "payment_status": "paid",
                            "last_payment_at": now(),
                            "last_period_end": max(
                                period_end, purchased[0].get("last_period_end", 0)
                            ),
                        },
                        purchased,
                    )
                )
            writes += [
                put(wallet_kind, user_id, bank, found),
                put(
                    "billing_cycles",
                    cycle_key,
                    {**marker, "credits": purchase["credits"], "purchase_id": purchase["id"]},
                ),
                put(
                    "wallet_events",
                    hash_token("stripe:" + cycle),
                    {
                        "user_id": user_id,
                        "actor_id": user_id,
                        "kind": "stripe_sandbox" if sandbox else "stripe_payment",
                        "amount": 0 if sandbox else purchase["credits"],
                        "created_at": now(),
                        "ledger_key": user_id + "_" + now().isoformat() + "_" + event_key,
                    },
                ),
            ]
        if purchase["mode"] == "subscription":
            ckey = hash_token(user_id + ":" + str(event["livemode"]))
            customer_row = store.read("billing_customers", ckey)
            if customer_row and customer_row[0].get("pending_purchase") == purchase["id"]:
                writes.append(
                    put(
                        "billing_customers",
                        ckey,
                        {**customer_row[0], "pending_purchase": "", "pending_until": 0},
                        customer_row,
                    )
                )
        try:
            store.commit(writes)
            return
        except store.Conflict:
            continue
    raise store.Unavailable()


def resolve_purchase(metadata):
    pid = metadata.get("haytile_purchase_id", "")
    if not re.fullmatch(r"[a-f0-9]{64}", pid):
        return None
    found = store.read("billing_purchases", pid)
    return found[0] if found else None


def apply_event(event):
    obj = event["data"]["object"]
    kind = event["type"]
    if event.get("livemode") != live():
        fail("STRIPE_MODE_MISMATCH", 400)
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        purchase = resolve_purchase(obj.get("metadata", {}))
        if (
            not purchase
            or purchase["livemode"] != int(event["livemode"])
            or purchase["mode"] != "payment"
            or obj.get("payment_status") != "paid"
        ):
            return
        session = stripe(
            "GET", "/checkout/sessions/" + obj["id"], params={"expand[]": "line_items"}
        )
        items = session.get("line_items", {}).get("data", [])
        if (
            session.get("customer") != purchase["customer_id"]
            or session.get("client_reference_id") != purchase["user_id"]
            or session.get("payment_status") != "paid"
            or session.get("currency") != purchase["currency"]
            or session.get("amount_total", 0) < purchase["unit_amount"]
            or len(items) != 1
            or items[0].get("quantity") != 1
            or items[0].get("price", {}).get("id") != purchase["price_id"]
        ):
            fail("STRIPE_PAYMENT_MISMATCH", 400)
        grant(event, purchase, "payment:" + purchase["id"])
    elif kind == "invoice.paid":
        sid = obj.get("subscription") or obj.get("parent", {}).get("subscription_details", {}).get(
            "subscription"
        )
        if not sid or obj.get("billing_reason") not in (
            "subscription_create",
            "subscription_cycle",
        ):
            return
        sub = stripe("GET", "/subscriptions/" + sid)
        purchase = resolve_purchase(sub.get("metadata", {}))
        if not purchase:
            return
        if (
            purchase["livemode"] != int(event["livemode"])
            or purchase["mode"] != "subscription"
            or sub.get("customer") != purchase["customer_id"]
            or obj.get("customer") != purchase["customer_id"]
            or obj.get("status") != "paid"
            or obj.get("currency") != purchase["currency"]
            or obj.get("amount_paid", 0) < purchase["unit_amount"]
        ):
            fail("STRIPE_PAYMENT_MISMATCH", 400)
        items = sub.get("items", {}).get("data", [])
        if (
            len(items) != 1
            or items[0].get("quantity") != 1
            or items[0].get("price", {}).get("id") != purchase["price_id"]
        ):
            fail("STRIPE_PAYMENT_MISMATCH", 400)
        end = max(
            (line.get("period", {}).get("end", 0) for line in obj.get("lines", {}).get("data", [])),
            default=0,
        )
        if not end:
            fail("STRIPE_PAYMENT_MISMATCH", 400)
        grant(event, purchase, "subscription:" + sid + ":" + str(end), end, sub)
    elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = stripe("GET", "/subscriptions/" + obj["id"])
        purchase = resolve_purchase(sub.get("metadata", {}))
        if not purchase:
            return
        if sub.get("status") not in ("canceled", "unpaid", "incomplete_expired"):
            return
        wallet_kind = "wallets" if event["livemode"] else "billing_sandbox_wallets"
        for _ in range(8):
            found = store.read(wallet_kind, purchase["user_id"])
            if not found or found[0].get("stripe_subscription_id") != sub["id"]:
                return
            bank = {**found[0], "plan": "free", "plan_expires_at": now()}
            try:
                store.commit([put(wallet_kind, purchase["user_id"], bank, found)])
                return
            except store.Conflict:
                continue
        raise store.Unavailable()
    elif kind in ("charge.refunded", "charge.dispute.created"):
        intent = obj.get("payment_intent")
        if not intent:
            return
        payment = stripe("GET", "/payment_intents/" + intent)
        purchase = resolve_purchase(payment.get("metadata", {}))
        if not purchase:
            charge = (
                obj if kind == "charge.refunded" else stripe("GET", "/charges/" + obj["charge"])
            )
            invoice_id = charge.get("invoice")
            if not invoice_id:
                matches = query("billing_customers", "customer_id", charge.get("customer", ""))
                purchase = next(
                    (
                        {"user_id": row["user_id"]}
                        for row in matches
                        if row["livemode"] == int(event["livemode"])
                    ),
                    None,
                )
                if not purchase:
                    return
            else:
                invoice = stripe("GET", "/invoices/" + invoice_id)
                sid = invoice.get("subscription") or invoice.get("parent", {}).get(
                    "subscription_details", {}
                ).get("subscription")
                if not sid:
                    return
                purchase = resolve_purchase(
                    stripe("GET", "/subscriptions/" + sid).get("metadata", {})
                )
        if not purchase:
            return
        risk_key = hash_token(event["id"])
        wallet_kind = "wallets" if event["livemode"] else "billing_sandbox_wallets"
        for _ in range(8):
            if store.read("billing_risks", risk_key):
                return
            account = store.read("accounts", purchase["user_id"])
            if not account or account[0].get("status") != "active":
                return
            found = store.read(wallet_kind, purchase["user_id"])
            bank = found[0] if found else wallets.base()
            bank["billing_hold"] = 1
            risk = {
                "id": risk_key,
                "user_id": purchase["user_id"],
                "event_id": event["id"],
                "kind": kind,
                "resolved": 0,
                "livemode": int(event["livemode"]),
                "created_at": now(),
            }
            try:
                store.commit(
                    [
                        put("billing_risks", risk_key, risk),
                        put("accounts", purchase["user_id"], account[0], account),
                        put(wallet_kind, purchase["user_id"], bank, found),
                    ]
                )
                return
            except store.Conflict:
                continue
        raise store.Unavailable()


@router.post("/v1/billing/webhook")
async def webhook(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 1048576:
            fail("FILE_SIZE", 413)
    if (
        not store.enabled()
        or not key_present()
        or not signature(bytes(raw), request.headers.get("stripe-signature", ""))
    ):
        fail("STRIPE_SIGNATURE_INVALID", 400)
    try:
        event = json.loads(raw)
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("data"), dict)
            or not isinstance(event["data"].get("object"), dict)
        ):
            raise ValueError()
        if (
            not isinstance(event.get("id"), str)
            or type(event.get("livemode")) is not bool
            or not isinstance(event.get("type"), str)
        ):
            raise ValueError()
        event["data"]["object"]
    except (ValueError, KeyError, TypeError):
        fail("STRIPE_EVENT_INVALID", 400)
    await asyncio.to_thread(apply_event, event)
    return {"received": True}


def cancel_for_user(user_id):
    if not store.enabled():
        return
    # Delete both sandbox and live customers if present, using the matching mode's key.
    for mode in (False, True):
        found = store.read("billing_customers", hash_token(user_id + ":" + str(mode)))
        if not found:
            continue
        if not mode and live():
            continue  # Sandbox customers cannot keep a real paid subscription active.
        if mode != live() or not key_present():
            fail("BILLING_ACCOUNT_DELETE_PENDING", 503)
        existing = stripe("GET", "/customers/" + found[0]["customer_id"])
        if not existing.get("deleted"):
            stripe("DELETE", "/customers/" + found[0]["customer_id"])


class ResolveRisk(BaseModel):
    revoke_credits: int = Field(ge=0, le=1000000)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/v1/admin/billing/risks/{risk_id}/resolve")
def resolve_risk(risk_id: str, body: ResolveRisk, user=Depends(admin)):
    if not store.enabled():
        fail("BILLING_NOT_CONFIGURED", 503)
    if not re.fullmatch("[a-f0-9]{64}", risk_id):
        fail("NOT_FOUND", 404)
    for _ in range(8):
        found = store.read("billing_risks", risk_id)
        if not found:
            fail("NOT_FOUND", 404)
        risk = found[0]
        if risk["resolved"]:
            return {"ok": True}
        wallet_kind = "wallets" if risk["livemode"] else "billing_sandbox_wallets"
        old = store.read(wallet_kind, risk["user_id"])
        bank = old[0] if old else wallets.base()
        if body.revoke_credits > bank["balance"] - bank["reserved"]:
            fail("BILLING_REVOKE_UNAVAILABLE", 409)
        others = query("billing_risks", "user_id", risk["user_id"])
        if len(others) >= 100:
            fail("BILLING_REVIEW_REQUIRED", 409)
        bank["balance"] -= body.revoke_credits
        bank["billing_hold"] = int(
            any(
                not row["resolved"] and row["id"] != risk_id and row["livemode"] == risk["livemode"]
                for row in others
            )
        )
        bank["updated_at"] = now()
        risk = {
            **risk,
            "resolved": 1,
            "reason": body.reason,
            "actor_id": user.id,
            "revoke_credits": body.revoke_credits,
            "resolved_at": now(),
        }
        event_id = hash_token("billing-risk-resolve:" + risk_id)
        event = {
            "user_id": risk["user_id"],
            "actor_id": user.id,
            "amount": -body.revoke_credits if risk["livemode"] else 0,
            "kind": "stripe_risk_resolve",
            "created_at": now(),
            "ledger_key": risk["user_id"] + "_" + now().isoformat() + "_" + event_id,
        }
        try:
            store.commit(
                [
                    put("billing_risks", risk_id, risk, found),
                    put(wallet_kind, risk["user_id"], bank, old),
                    put("wallet_events", event_id, event),
                    store.audit_write(user.id, "billing.risk.resolve", risk["user_id"]),
                ]
            )
            return {"ok": True}
        except store.Conflict:
            continue
    raise store.Unavailable()
