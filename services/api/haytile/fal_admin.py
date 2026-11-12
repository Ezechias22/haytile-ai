"""Private fal discovery / verification / activation. Never creates inference jobs."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import fal_catalog, fal_client, fal_inputs
from .db import now
from .main import admin, fail, limit
from .provider_errors import ProviderError

router = APIRouter()


def public_profile(profile):
    return {key: value for key, value in profile.items() if key not in ("input_schema",)}


def read_profile(identifier):
    profile = fal_catalog.get(identifier)
    if not profile:
        fail("NOT_FOUND", 404)
    return profile


def current_rate(profile):
    raw = fal_client.pricing(profile["endpoint_id"])
    price = next(
        (row for row in raw.get("prices", []) if row.get("endpoint_id") == profile["endpoint_id"]),
        None,
    )
    if not price or price.get("currency") != "USD":
        raise ProviderError("PRICING_NOT_VERIFIED")
    value = Decimal(str(price["unit_price"]))
    if not value.is_finite() or not 0 < value < 1000:
        raise ProviderError("PRICING_NOT_VERIFIED")
    candidate = {
        **profile,
        "price_unit": price["unit"],
        "unit_price": str(value),
        "price_verified": True,
    }
    # A price unit that cannot be bounded by this adapter is not safe to activate.
    fal_inputs.billing_units(candidate, "Pricing preview", {"language": "en"})
    return candidate


@router.get("/v1/admin/fal")
def settings(user=Depends(admin)):
    return {
        "key_present": fal_client.ready(),
        "profiles": [public_profile(row) for row in fal_catalog.profiles()],
        "dashboard_url": "https://fal.ai/dashboard/keys",
        "generation_test_requests": 0,
    }


@router.get("/v1/admin/fal/catalog")
def discover(
    q: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=80),
    cursor: str = Query(default="", max_length=1000),
    user=Depends(admin),
):
    limit("fal-discovery:" + user.id, 30, 60)
    try:
        data = fal_client.catalog(q, category, cursor)
        result = []
        supported = {row["endpoint_id"] for row in fal_catalog.profiles()}
        for row in data.get("models", []):
            identifier = fal_client.endpoint(row["endpoint_id"])
            metadata = row.get("metadata") or {}
            result.append(
                {
                    "endpoint_id": identifier,
                    "label": metadata.get("display_name", identifier),
                    "category": metadata.get("category", ""),
                    "description": metadata.get("description", "")[:1000],
                    "integrated": identifier in supported,
                    "url": "https://fal.ai/models/" + identifier,
                    "license_type": metadata.get("license_type"),
                }
            )
        return {
            "models": result,
            "next_cursor": data.get("next_cursor"),
            "has_more": data.get("has_more", False),
        }
    except ProviderError as exc:
        fail(str(exc), 503)


@router.post("/v1/admin/fal/models/{identifier}/verify")
def verify(identifier: str, user=Depends(admin)):
    limit("fal-pricing:" + user.id, 20, 60)
    profile = read_profile(identifier)
    try:
        found = fal_client.catalog(identifier=profile["endpoint_id"], expand=True)
        model = next(
            (
                row
                for row in found.get("models", [])
                if row.get("endpoint_id") == profile["endpoint_id"]
            ),
            None,
        )
        if (
            not model
            or not model.get("openapi")
            or (model.get("metadata") or {}).get("status") == "deprecated"
        ):
            fail("MODEL_NOT_IN_ACCOUNT", 409)
        # Verify that all model-bound inputs still exist before approval.
        native = model["openapi"].get("components", {}).get("schemas", {})
        schema = next(
            (
                value
                for name, value in native.items()
                if name.endswith("Input")
                and value.get("properties", {}).get("prompt")
                or name.endswith("Input")
                and value.get("properties", {}).get("tags")
                or name.endswith("Input")
                and value.get("properties", {}).get("image_url")
            ),
            None,
        )
        if not schema:
            raise ProviderError("FAL_SCHEMA_CHANGED")
        expected_fields = set(profile.get("constants", {})) | set(profile.get("fields", {}))
        if not expected_fields <= set(schema.get("properties", {})):
            raise ProviderError("FAL_SCHEMA_CHANGED")
        sample = {"language": "en", "aspect": "1:1"}
        if profile.get("reference_required"):
            sample.update(
                reference_asset_id="verification-only",
                _fal_reference_url="https://example.invalid/reference.png",
            )
        native_payload = fal_inputs.payload(profile, "Verification preview", sample)
        if not set(schema.get("required", [])) <= set(native_payload):
            raise ProviderError("FAL_SCHEMA_CHANGED")
        profile = current_rate(profile)
        profile.update(enabled=False, pricing_checked_at=now().isoformat(), input_schema=schema)
        fal_catalog.save(profile, user.id)
        return public_profile(profile)
    except ProviderError as exc:
        fail(str(exc), 409)


class Activation(BaseModel):
    enabled: bool
    operator_billing_ack: bool = False
    license_ack: bool = False
    expected_unit_price: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    expected_unit: str = Field(default="", max_length=80)
    markup: str = Field(default="4", max_length=10)
    allow_paused_studio: bool = False


@router.put("/v1/admin/fal/models/{identifier}")
def activate(identifier: str, body: Activation, user=Depends(admin)):
    profile = read_profile(identifier)
    try:
        if body.enabled:
            if not body.operator_billing_ack or not body.license_ack:
                fail("OPERATOR_BILLING_ACK_REQUIRED", 409)
            if not profile.get("price_verified"):
                fail("PRICING_NOT_VERIFIED", 409)
            checked = current_rate(profile)
            if (
                Decimal(checked["unit_price"]) != body.expected_unit_price
                or checked["price_unit"] != body.expected_unit
            ):
                fail("PRICE_CHANGED", 409)
            profile = checked
        profile.update(
            enabled=body.enabled,
            markup=body.markup,
            allow_paused_studio=body.allow_paused_studio if profile["studio"] == "video" else False,
        )
        fal_catalog.save(profile, user.id)
        return public_profile(profile)
    except ProviderError as exc:
        fail(str(exc), 409)
