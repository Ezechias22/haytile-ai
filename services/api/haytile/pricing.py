"""Server quotes from dated official rates plus an explicit Haytile reserve/margin.

1 reference credit = US$0.01. This is an app policy, not a Google price or a
Google billing unit. Credit purchases use separately configured Stripe offers.
Free text still costs the operator money; paid
images are enabled explicitly by the operator.
"""

import math
import os
from decimal import ROUND_CEILING, Decimal

from fastapi import HTTPException

SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
VERSION = "google-2026-11-04-video-margin-v2"
# USD per generated request, as listed on the official Standard pricing page.
MUSIC_USD = {
    "lyria-3-clip-preview": Decimal("0.04"),
    "lyria-3-pro-preview": Decimal("0.08"),
    "lyria-3.5": Decimal("0.08"),
}
# Use announced regular (post-introductory-discount) rates as the reserve basis.
# Tuples are input-text/output-audio USD per million tokens.
VOICE_RATES = {
    "gemini-3.8-flash-lite-tts": (Decimal("1"), Decimal("12")),
    "gemini-3.8-flash-tts": (Decimal("1"), Decimal("18")),
    "gemini-3.1-flash-tts-preview": (Decimal("1"), Decimal("20")),
    "gemini-2.5-flash-preview-tts": (Decimal("0.5"), Decimal("10")),
    "gemini-2.5-pro-preview-tts": (Decimal("1"), Decimal("20")),
}
VIDEO = "gemini-omni-1.1-flash"
CLIP_SECONDS = 8
# Official 720p output: 5,792 tokens/second at $17.50 per million tokens.
VIDEO_SECOND_USD = Decimal("5792") * Decimal("17.50") / Decimal("1000000")
# App reserves, not claims about a separate Google fee:
INPUT_AND_OPERATION_RESERVE = Decimal("0.10")
DRAMA_PLAN_AND_REFERENCES_RESERVE = Decimal("2.25")
MARKUP = Decimal("4")
VIDEO_MARKUP = Decimal("1.5")
CREDIT_USD = Decimal("0.01")


def verified():
    return os.environ.get("HAYTILE_PRICING_POLICY", "operator") == "verified"


def credits_for(cost, markup=MARKUP):
    return int((cost * markup / CREDIT_USD).to_integral_value(rounding=ROUND_CEILING))


# Official 1K output-image USD, input/output-text USD per million tokens.
IMAGE_RATES = {
    "gemini-3.1-flash-lite-image": (Decimal("0.0336"), Decimal("0.25"), Decimal("1.50")),
    "gemini-3.1-flash-image": (Decimal("0.067"), Decimal("0.50"), Decimal("3")),
    "gemini-3-pro-image": (Decimal("0.134"), Decimal("2"), Decimal("12")),
    "gemini-2.5-flash-image": (Decimal("0.039"), Decimal("0.30"), Decimal("2.50")),
    "gemini-nano-banana-2.1": (Decimal("0.0336"), Decimal("1.50"), Decimal("7.50")),
}


def paid_images():
    return os.environ.get("HAYTILE_PAID_IMAGES") == "1"


def image_quote(model_id, prompt="", params=None):
    if model_id not in IMAGE_RATES:
        raise HTTPException(409, detail="PRICING_NOT_VERIFIED")
    image, inp, out = IMAGE_RATES[model_id]
    # Conservative UTF-8 byte budget, output cap and explicit operation reserve.
    input_budget = (
        1000
        + len(prompt.encode("utf-8"))
        + (40000 if (params or {}).get("reference_asset_id") else 0)
    )
    cost = image + (inp * input_budget + out * 2048) / Decimal("1000000") + Decimal("0.002")
    # Lower image-specific markup; not a Google fee or a guaranteed retail profit.
    return int((cost * 2 / CREDIT_USD).to_integral_value(rounding=ROUND_CEILING))


def base_credits(studio, model_id, operator_credits=0):
    if studio == "text" or (studio == "image" and not paid_images()):
        return 0
    if studio == "image" and verified():
        return max(operator_credits, image_quote(model_id))
    if not verified():
        return operator_credits
    if studio == "minidrama":
        return operator_credits
    if studio == "music" and model_id in MUSIC_USD:
        return max(operator_credits, credits_for(MUSIC_USD[model_id]))
    if studio == "video" and model_id == VIDEO:
        # Reserve up to 10 native seconds per request although planning uses 8s.
        return max(
            operator_credits,
            credits_for(VIDEO_SECOND_USD * 10 + INPUT_AND_OPERATION_RESERVE, VIDEO_MARKUP),
        )
    if studio == "voice" and model_id in VOICE_RATES:
        inp, out = VOICE_RATES[model_id]
        cost = (inp * 4000 + out * 4096) / Decimal("1000000") + Decimal("0.01")
        return max(operator_credits, credits_for(cost))
    raise HTTPException(409, detail="PRICING_NOT_VERIFIED")


def quote(
    studio,
    model_id,
    prompt,
    params,
    operator_credits=0,
    render_config=None,
    video_credits=0,
):
    if studio == "music" and "duration" in params:
        duration = params["duration"]
        if type(duration) is not int or not 30 <= duration <= 300:
            raise HTTPException(400, detail="MUSIC_DURATION_INVALID")
        if model_id == "lyria-3-clip-preview" and duration != 30:
            raise HTTPException(400, detail="MUSIC_CLIP_DURATION_INVALID")
    from .music import target_seconds

    unit = base_credits(studio, model_id, operator_credits)
    clip_count = 0
    voice_tokens = 0
    if studio == "text" or (studio == "image" and not paid_images()):
        total = 0
    elif studio == "image" and verified():
        total = max(operator_credits, image_quote(model_id, prompt, params))
    elif studio == "video":
        clip_count = math.ceil(params.get("duration", 8) / CLIP_SECONDS)
        total = (
            unit * clip_count if verified() else unit * math.ceil(params.get("duration", 8) / 10)
        )
    elif studio == "voice" and verified():
        units = max(1, math.ceil(len(prompt) / 1000))
        total = unit * units
        voice_tokens = min(32768, 4096 * units)
    elif studio == "minidrama" and params.get("mode") == "episode":
        clip_count = math.ceil(params.get("duration", 16) / CLIP_SECONDS)
        if verified():
            if not render_config:
                raise HTTPException(409, detail="PROVIDER_SETUP_REQUIRED")
            per_clip = base_credits("video", render_config["video"], video_credits)
            total = clip_count * per_clip + credits_for(
                DRAMA_PLAN_AND_REFERENCES_RESERVE, VIDEO_MARKUP
            )
        else:
            total = unit + clip_count * video_credits
    else:
        total = unit
    return {
        "credits": total,
        "free": total == 0,
        "clip_count": clip_count,
        "voice_token_limit": voice_tokens,
        "music_target_seconds": target_seconds(prompt, model_id) if studio == "music" else None,
        "image_size": "1K" if studio == "image" and paid_images() else None,
        "pricing_version": VERSION if verified() else "operator-configured",
        "reference_unit_usd": str(CREDIT_USD),
        "reference_total_usd": str(CREDIT_USD * total),
        "pricing_source": SOURCE,
    }
