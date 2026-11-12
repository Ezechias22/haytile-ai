"""Server-owned model choices. Client input never sets model price or approval."""

import json
import os
import re
from dataclasses import dataclass

from fastapi import HTTPException

from . import pricing
from .db import Model

STUDIOS = {"image", "text", "voice", "music", "video", "minidrama"}
PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
TERMS = "https://ai.google.dev/gemini-api/terms"


@dataclass
class Choice:
    studio: str
    model_id: str
    label: str
    credits: int
    enabled: bool
    catalog_check: bool = True
    provider: str = "google"
    terms_url: str = TERMS
    unavailable_reason: str | None = None
    pricing_url: str = PRICING
    fal_profile: dict | None = None


def configured_choices(db, studio):
    try:
        entries = json.loads(os.environ.get("HAYTILE_MODEL_CHOICES", "[]"))
        if not isinstance(entries, list) or len(entries) > 64:
            raise ValueError()
        result = {}
        for entry in entries:
            if (
                entry.get("studio") not in STUDIOS
                or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", entry.get("model_id", ""))
                or type(entry.get("credits", 0)) is not int
                or not 0 <= entry.get("credits", 0) <= 100000
                or (
                    (
                        entry["studio"] == "text"
                        or (entry["studio"] == "image" and not pricing.paid_images())
                    )
                    and entry.get("credits", 0) != 0
                )
                or not isinstance(entry.get("label", entry["model_id"]), str)
            ):
                raise ValueError()
            if entry["studio"] != studio:
                continue
            result[entry["model_id"]] = Choice(
                studio,
                entry["model_id"],
                entry.get("label", entry["model_id"])[:160],
                entry.get("credits", 0),
                entry.get("enabled") is True
                and os.environ.get("HAYTILE_OPERATOR_BILLING_ACK") == "1",
            )
        row = db.get(Model, studio)
        if row:
            label = result[row.model_id].label if row.model_id in result else row.model_id
            result[row.model_id] = Choice(
                studio,
                row.model_id,
                label,
                0
                if studio == "text" or (studio == "image" and not pricing.paid_images())
                else row.credits,
                row.enabled,
                False,
                row.provider,
                row.terms_url,
            )
            if not row.enabled:
                for choice in result.values():
                    choice.enabled = False
        for choice in result.values():
            try:
                choice.credits = pricing.base_credits(studio, choice.model_id, choice.credits)
            except HTTPException:
                choice.enabled = False
                choice.unavailable_reason = "PRICING_NOT_VERIFIED"
        from . import fal_catalog

        for profile in fal_catalog.profiles():
            if profile["studio"] != studio:
                continue
            reason = fal_catalog.availability(profile)
            active = reason is None and os.environ.get("HAYTILE_OPERATOR_BILLING_ACK") == "1"
            if row and not row.enabled and not profile.get("allow_paused_studio"):
                active = False
                reason = "STUDIO_DISABLED"
            credits = 0
            if profile.get("price_verified"):
                try:
                    credits = pricing.base_credits(studio, profile["id"])
                except HTTPException:
                    reason, active = "PRICING_NOT_VERIFIED", False
            result[profile["id"]] = Choice(studio, profile["id"], profile["label"] + " · fal.ai", credits, active,
                False, "fal", profile["terms_url"], reason, profile["price_source"], profile)
        return list(result.values())
    except (ValueError, TypeError, AttributeError, KeyError):
        raise RuntimeError("MODEL_CHOICES_CONFIGURATION_INVALID") from None


def select_choice(db, studio, model_id):
    return next(
        (choice for choice in configured_choices(db, studio) if choice.model_id == model_id),
        None,
    )
