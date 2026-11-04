"""Firestore authority for manual credits/plans. No SQL balance mirroring.

Paid generation remains gated until job reservations/settlement are durable too.
"""

import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException

from . import accounts as store
from .db import now


def enabled():
    return store.enabled()


def fail(code, status=409):
    raise HTTPException(status, detail=code)


def base():
    return {
        "balance": 0,
        "reserved": 0,
        "plan": "free",
        "plan_expires_at": now(),
        "updated_at": now(),
    }


def validate(data):
    if (
        type(data.get("balance")) is not int
        or type(data.get("reserved")) is not int
        or not 0 <= data["reserved"] <= data["balance"] <= 1000000000
        or data.get("plan") not in ("free", "creator", "pro")
    ):
        raise store.Unavailable()
    return data


def snapshot(user_id):
    found = store.read("wallets", user_id)
    data = validate(found[0]) if found else base()
    return {
        "billing_hold": data.get("billing_hold", 0),
        "balance": data["balance"],
        "reserved": data["reserved"],
        "plan": data["plan"] if data["plan_expires_at"] > now() else "free",
        "plan_expires_at": data["plan_expires_at"] if data["plan"] != "free" else None,
    }


def grant(email, amount, actor, key, plan=None, days=None, reason=""):
    target = store.by_email(email.strip().lower())
    if not target:
        fail("NOT_FOUND", 404)
    user_id = target["id"]
    kind = "admin_plan" if plan is not None else "admin_grant"
    event_id = hashlib.sha256((actor + ":" + kind + ":" + key).encode()).hexdigest()
    payload = {
        "user_id": user_id,
        "amount": amount,
        "plan": plan,
        "days": days,
        "reason": reason,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    for _ in range(8):
        event = store.read("wallet_events", event_id)
        if event:
            if event[0]["fingerprint"] != fingerprint:
                fail("IDEMPOTENCY_CONFLICT")
            return {"ok": True}
        account = store.read("accounts", user_id)
        if not account or account[0].get("status") != "active":
            fail("NOT_FOUND", 404)
        found = store.read("wallets", user_id)
        data = validate(found[0]) if found else base()
        if data["balance"] + amount > 1000000000:
            fail("WALLET_LIMIT")
        data["balance"] += amount
        data["updated_at"] = now()
        if plan is not None:
            data["plan"] = plan
            data["plan_expires_at"] = now() + timedelta(days=days)
        timestamp = now()
        event = {
            "user_id": user_id,
            "actor_id": actor,
            "amount": amount,
            "kind": kind,
            "fingerprint": fingerprint,
            "created_at": timestamp,
            "ledger_key": user_id + "_" + timestamp.isoformat() + "_" + event_id,
        }
        audit = {
            "user_id": user_id,
            "actor_id": actor,
            "action": "plan.assign" if plan is not None else "credits.grant",
            "amount": amount,
            "created_at": timestamp,
        }
        if plan is not None:
            audit.update(plan=plan, days=days, reason=reason)
        try:
            store.commit(
                [
                    store.update_write(
                        "accounts", user_id, account[0], version=account[1]
                    ),
                    store.update_write(
                        "wallets",
                        user_id,
                        data,
                        version=found[1] if found else None,
                        create=not bool(found),
                    ),
                    store.update_write("wallet_events", event_id, event, create=True),
                    store.update_write("account_audit", event_id, audit, create=True),
                ]
            )
            return {"ok": True}
        except store.Conflict:
            continue
    raise store.Unavailable()


def history(user_id):
    prefix = user_id + "_"
    response = store.request(
        "POST",
        "/documents:runQuery",
        json={
            "structuredQuery": {
                "from": [{"collectionId": "haytile_wallet_events"}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "ledger_key"},
                                    "op": "GREATER_THAN_OR_EQUAL",
                                    "value": {"stringValue": prefix},
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "ledger_key"},
                                    "op": "LESS_THAN",
                                    "value": {"stringValue": prefix + "\uf8ff"},
                                }
                            },
                        ],
                    }
                },
                "orderBy": [
                    {"field": {"fieldPath": "ledger_key"}, "direction": "DESCENDING"}
                ],
                "limit": 100,
            }
        },
    )
    if response.status_code != 200:
        raise store.Unavailable()
    return [
        {
            "id": row["document"]["name"].rsplit("/", 1)[1],
            **{key: data[key] for key in ("amount", "kind", "created_at")},
        }
        for row in response.json()
        if "document" in row
        for data in [store.decode(row["document"])]
    ]
