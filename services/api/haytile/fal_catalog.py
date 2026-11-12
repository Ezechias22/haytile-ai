"""Durable, operator-approved fal model profiles. Model IDs are opaque aliases.

Public catalog discovery does NOT approve arbitrary endpoints for paid work.
Quotes and jobs use the same bounded server-owned input and pricing policy.
"""

import copy
import hashlib
import json
import os
import threading
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select

from . import accounts
from .db import Audit, Session, now
from .provider_errors import ProviderError

DEFAULTS = json.loads(Path(__file__).with_name("fal_models.json").read_text())
STUDIOS = {"image", "music", "voice", "text", "video", "minidrama"}
ADAPTERS = {entry["adapter"] for entry in DEFAULTS}
_cache = None
_cache_until = 0
_lock = threading.RLock()


def alias(studio, endpoint_id):
    return "fal-" + hashlib.sha256((studio + ":" + endpoint_id).encode()).hexdigest()[:24]


def invalidate():
    global _cache_until
    _cache_until = 0


def profiles():
    global _cache, _cache_until
    with _lock:
        if _cache is not None and time.monotonic() < _cache_until:
            return copy.deepcopy(_cache)
        values = {item["id"]: item for item in copy.deepcopy(DEFAULTS)}
        if accounts.enabled():
            found = accounts.read("provider_config", "fal_models")
            overrides = json.loads(found[0]["payload"]) if found else []
        else:
            with Session() as db:
                row = db.scalar(
                    select(Audit)
                    .where(Audit.action == "fal.models.configure")
                    .order_by(Audit.created_at.desc())
                    .limit(1)
                )
                overrides = row.details.get("profiles", []) if row else []
        for item in overrides:
            validate(item)
            values[item["id"]] = item
        _cache = list(values.values())
        _cache_until = time.monotonic() + (15 if accounts.enabled() else 0)
        return copy.deepcopy(_cache)


def get(identifier):
    return next((item for item in profiles() if item["id"] == identifier), None)


def validate(item):
    from .fal_client import endpoint

    if (
        item.get("studio") not in STUDIOS
        or item.get("adapter") not in ADAPTERS
        or item.get("id") != alias(item.get("studio", ""), endpoint(item.get("endpoint_id")))
        or len(json.dumps(item)) > 100000
        or not item.get("price_source", "").startswith("https://fal.ai/")
    ):
        raise ProviderError("FAL_PROFILE_INVALID")
    try:
        price = Decimal(item.get("unit_price", "0"))
        markup = Decimal(item.get("markup", "4"))
        if not price.is_finite() or price < 0 or not markup.is_finite() or not 1 <= markup <= 20:
            raise ValueError()
        if item.get("enabled") and (not item.get("price_verified") or price <= 0):
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        raise ProviderError("PRICING_NOT_VERIFIED") from None


def save(profile, actor, expected_version=None):
    validate(profile)
    with _lock:
        invalidate()
        found = accounts.read("provider_config", "fal_models") if accounts.enabled() else None
        if accounts.enabled():
            updated = {item["id"]: item for item in copy.deepcopy(DEFAULTS)}
            for item in json.loads(found[0]["payload"]) if found else []:
                validate(item)
                updated[item["id"]] = item
        else:
            updated = {item["id"]: item for item in profiles()}
        updated[profile["id"]] = profile
        if len(updated) > 128:
            raise ProviderError("FAL_PROFILE_LIMIT")
        data = list(updated.values())
        if len(json.dumps(data).encode()) > 800000:
            raise ProviderError("FAL_PROFILE_LIMIT")
        if accounts.enabled():
            version = found[1] if found else None
            if expected_version is not None and expected_version != version:
                raise ProviderError("FAL_PROFILE_CONFLICT")
            accounts.commit(
                [
                    accounts.update_write(
                        "provider_config",
                        "fal_models",
                        {"payload": json.dumps(data), "updated_at": now(), "actor_id": actor},
                        version=version,
                        create=not found,
                    ),
                    accounts.audit_write(actor, "fal.models.configure", profile["id"]),
                ]
            )
        with Session.begin() as db:
            db.add(
                Audit(
                    actor_id=actor,
                    action="fal.models.configure",
                    details={"profiles": data, "model_id": profile["id"]},
                )
            )
        invalidate()
    return profile


def key_ready():
    return bool((os.environ.get("FAL_KEY") or os.environ.get("Fal_key", "")).strip())


def availability(profile):
    if not profile.get("price_verified"):
        return "PRICING_NOT_VERIFIED"
    if not key_ready():
        return "FAL_KEY_MISSING"
    if not profile.get("enabled"):
        return "MODEL_NOT_APPROVED"
    return None
