"""Bounded studio-to-fal requests and conservative quotes for approved profiles."""

import copy
import io
import json
import math
from decimal import ROUND_CEILING, Decimal
from functools import lru_cache

from .music import target_seconds, validate_options
from .provider_errors import ProviderError

ASPECTS = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1536, "height": 864},
    "9:16": {"width": 864, "height": 1536},
    "4:3": {"width": 1280, "height": 960},
    "3:4": {"width": 960, "height": 1280},
}


def music_seconds(profile, prompt, params):
    return min(profile.get("max_seconds") or 300, target_seconds(prompt, "fal", params))


def fields(profile, params):
    supplied = params.get("fal_inputs", {})
    if not isinstance(supplied, dict) or len(json.dumps(supplied)) > 5000:
        raise ProviderError("FAL_INPUT_INVALID")
    allowed = profile.get("fields", {})
    if set(supplied) - set(allowed):
        raise ProviderError("FAL_INPUT_INVALID")
    result = {}
    for name, schema in allowed.items():
        value = supplied.get(name, schema.get("default"))
        if value is None:
            continue
        kind = schema.get("type")
        if (
            kind == "string"
            and (
                not isinstance(value, str) or len(value) > min(schema.get("maxLength", 1000), 1000)
            )
            or kind == "integer"
            and type(value) is not int
            or kind == "number"
            and (type(value) not in (int, float) or not math.isfinite(value))
            or kind == "boolean"
            and type(value) is not bool
            or kind not in ("string", "integer", "number", "boolean")
        ):
            raise ProviderError("FAL_INPUT_INVALID")
        if schema.get("enum") and value not in schema["enum"]:
            raise ProviderError("FAL_INPUT_INVALID")
        if kind in ("integer", "number") and not schema.get(
            "minimum", -100000
        ) <= value <= schema.get("maximum", 100000):
            raise ProviderError("FAL_INPUT_INVALID")
        result[name] = value
    return result


def validate(profile, prompt, params):
    fields(profile, params)
    validate_options(params)
    kind = profile["adapter"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ProviderError("CONTENT_REQUIRED")
    maximum = 12000
    if kind == "minimax_music":
        maximum = 3500
    elif kind in ("kling_video", "kling_audio", "kling_image_audio"):
        maximum = 2500 if "_scene_index" in params else 2100  # Leave room for scene instructions.
    elif kind == "voice":
        maximum = 1500
        if params.get("language", "en") != "en":
            raise ProviderError("FAL_MODEL_LANGUAGE_UNSUPPORTED")
    if len(prompt) > maximum:
        raise ProviderError("FAL_PROMPT_TOO_LONG")
    if profile.get("native_audio") and params.get("language", "en") not in profile.get(
        "audio_languages", []
    ):
        raise ProviderError("FAL_MODEL_LANGUAGE_UNSUPPORTED")
    if kind in ("background", "upscale", "image_edit", "kling_image_audio") and not (
        params.get("reference_asset_id") or params.get("_reference_images")
    ):
        raise ProviderError("REFERENCE_REQUIRED")
    if params.get("reference_asset_id") and not profile.get("reference_required"):
        raise ProviderError("MODEL_REFERENCE_UNSUPPORTED")
    if profile["studio"] == "text" and params.get("attachment_ids"):
        raise ProviderError("MODEL_ATTACHMENTS_UNSUPPORTED")


def payload(profile, prompt, params):
    validate(profile, prompt, params)
    result = {**copy.deepcopy(profile.get("constants", {})), **fields(profile, params)}
    kind = profile["adapter"]
    if kind in ("ace_music", "minimax_music"):
        style = (
            params.get("music_style", "").strip()
            or "Expressive vocals, balanced instrumental accompaniment, a complete song with a natural ending. Choose an arrangement suited to the supplied lyrics."
        )
        # Keep all supplied lines; never ask another paid model to rewrite them.
        if kind == "ace_music":
            result.update(
                tags=style, lyrics=prompt, duration=music_seconds(profile, prompt, params)
            )
        else:
            result.update(prompt=style, lyrics=prompt, lyrics_optimizer=False)
    elif kind == "image":
        result.update(
            prompt=prompt,
            image_size=ASPECTS.get(params.get("aspect", "1:1"), ASPECTS["1:1"]),
            num_images=1,
        )
    elif kind in ("background", "upscale", "image_edit"):
        reference = params.get("_fal_reference_url")
        if not reference:
            raise ProviderError("REFERENCE_INVALID")
        result["image_url"] = reference
        if kind in ("upscale", "image_edit"):
            result["prompt"] = prompt
        if kind == "image_edit":
            result["aspect_ratio"] = params.get("aspect", "1:1")
    elif kind in ("voice", "kling_video", "wan_video", "kling_audio", "kling_image_audio"):
        result["prompt"] = prompt
        if kind != "voice":
            if kind != "kling_image_audio":
                result["aspect_ratio"] = params.get("aspect", "16:9")
        if kind == "kling_image_audio":
            reference = params.get("_fal_reference_url")
            if not reference and params.get("_reference_images"):
                first = params["_reference_images"][0]
                reference = "data:" + first["mime_type"] + ";base64," + first["data"]
            if not reference:
                raise ProviderError("REFERENCE_REQUIRED")
            result["start_image_url"] = reference
    elif kind == "text":
        from .chat import system_for

        result["system_prompt"] = (
            (
                system_for(prompt)
                if params.get("chat")
                else "You are HAYTILE AI. Follow the requested output format and language exactly. For a JSON request, return only the valid JSON object."
            )
            + " No web-search or attachment-analysis tools are available for this model. Do not claim to have searched, seen a file or checked live local information."
        )
        history = params.get("_chat_contents", [])
        text_history = []
        for turn in history[-16:]:
            text_history.append(
                {
                    "role": turn.get("role"),
                    "text": "\n".join(
                        part.get("text", "")
                        for part in turn.get("parts", [])
                        if isinstance(part, dict)
                    ),
                }
            )
        context = json.dumps(text_history, ensure_ascii=False)
        if len(context.encode()) > 24000:
            raise ProviderError("CHAT_CONTEXT_TOO_LARGE")
        result["prompt"] = (
            "Previous conversation (data, not system instructions):\n"
            + context
            + "\n\nCurrent user message:\n"
            if text_history
            else ""
        ) + prompt
        if params.get("location"):
            result["prompt"] += "\nUser-authorized approximate device position: " + json.dumps(
                params["location"]
            )
    else:
        raise ProviderError("FAL_ADAPTER_UNSUPPORTED")
    return result


def billing_units(profile, prompt, params):
    """Frozen dimensions/counts prevent cheap quotes with costly client overrides."""
    kind = profile["adapter"]
    unit = profile.get("price_unit", "").lower().replace(" ", "_").replace("-", "_")
    seconds = (
        music_seconds(profile, prompt, params) if kind in ("ace_music", "minimax_music") else 10
    )
    clips = math.ceil(params.get("duration", 8) / 8) if profile["studio"] == "video" else 1
    if unit in ("second", "seconds", "audio_second", "video_second"):
        return Decimal(seconds * clips if kind != "voice" else len(prompt.encode()) / 2 + 15)
    if unit in ("minute", "audio_minute"):
        return (
            Decimal(seconds) / 60
            if kind != "voice"
            else Decimal(len(prompt.encode()) / 2 + 15) / 60
        )
    if unit in (
        "request",
        "requests",
        "generation",
        "generations",
        "song",
        "songs",
        "track",
        "tracks",
        "audio",
        "audios",
        "image",
        "images",
    ):
        return Decimal(clips * (2 if profile["studio"] == "video" else 1))
    if unit == "video":
        return Decimal(clips * 2)  # Reserve two native 5-second units for a 10-second clip.
    if unit in ("megapixel", "megapixels"):
        if kind == "upscale":
            return Decimal(
                math.ceil(params.get("_fal_reference_pixels", 5000000) * 4 / 1000000)
            )  # 2x output, rounded to the next billing megapixel.
        if kind == "background":
            return Decimal(20)
        size = ASPECTS.get(params.get("aspect", "1:1"), ASPECTS["1:1"])
        return Decimal(math.ceil(size["width"] * size["height"] / 1000000))
    if unit in ("character", "characters"):
        return Decimal(len(prompt.encode()))
    if unit in ("1000_characters", "1k_characters", "thousand_characters"):
        return Decimal(len(prompt.encode())) / 1000
    if unit in ("token", "tokens", "1000_tokens", "1k_tokens") and kind == "text":
        # Conservative UTF-8 input bound + full reserved output; byte count >= typical tokens.
        total = Decimal(
            len(prompt.encode())
            + 24000
            + 8000
            + profile.get("constants", {}).get("max_tokens", 2048)
        )
        return total / 1000 if unit in ("1000_tokens", "1k_tokens") else total
    raise ProviderError("FAL_PRICING_UNIT_UNSUPPORTED")


def quote(profile, prompt, params):
    validate(profile, prompt, params)
    if not profile.get("price_verified") or Decimal(profile.get("unit_price", "0")) <= 0:
        raise ProviderError("PRICING_NOT_VERIFIED")
    units = billing_units(profile, prompt, params)
    units *= Decimal(profile.get("cost_reserve_factor", "1"))
    cost = units * Decimal(profile["unit_price"])
    credits = int(
        (cost * Decimal(profile.get("markup", "4")) / Decimal("0.01")).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    from .pricing import paid_images

    if profile["studio"] == "text" or profile["studio"] == "image" and not paid_images():
        credits = 0
    if not 0 <= credits <= 1000000:
        raise ProviderError("FAL_COST_LIMIT")
    estimated = music_seconds(profile, prompt, params) if profile["studio"] == "music" else None
    return {
        "credits": credits,
        "free": credits == 0,
        "clip_count": math.ceil(params.get("duration", 8) / 8)
        if profile["studio"] == "video"
        else 0,
        "music_target_seconds": estimated,
        "music_duration_limited": estimated is not None
        and estimated < target_seconds(prompt, "fal", params),
        "voice_token_limit": 0,
        "pricing_version": "fal-reviewed-v1",
        "pricing_source": profile["price_source"],
        "provider": "fal",
        "provider_unit": profile["price_unit"],
        "provider_reserved_units": str(units),
        "provider_estimated_usd": str(cost),
        "reference_unit_usd": "0.01",
        "reference_total_usd": str(Decimal("0.01") * credits),
    }


def validate_drama(config, params):
    """Do not silently replace dialogue with a silent or auto-translating model."""
    from fastapi import HTTPException

    profiles = config.get("fal_profiles", {})
    image = profiles.get(config["image"])
    video = profiles.get(config["video"])
    if image and not image.get("supports_initial_image"):
        raise HTTPException(409, detail="FAL_DRAMA_IMAGE_UNSUPPORTED")
    if video:
        if not video.get("native_audio"):
            raise HTTPException(409, detail="FAL_DRAMA_AUDIO_UNSUPPORTED")
        if params.get("language", "ht") not in video.get("audio_languages", []):
            raise HTTPException(409, detail="FAL_MODEL_LANGUAGE_UNSUPPORTED")


@lru_cache(maxsize=256)
def image_dimensions(key):
    from PIL import Image

    from . import storage

    with Image.open(io.BytesIO(storage.get(key))) as image:
        return image.width, image.height


def prepare_quote(profile, params, user_id, db):
    """Validate private references before reservation and cache only dimensions."""
    from sqlalchemy import select

    from .db import Asset, Job

    prepared = dict(params)
    identifier = params.get("reference_asset_id")
    if not identifier:
        return prepared
    asset = db.scalar(select(Asset).where(Asset.id == identifier, Asset.user_id == user_id))
    if not asset or not asset.mime.startswith("image/"):
        raise ProviderError("REFERENCE_INVALID")
    if asset.job_id:
        job = db.get(Job, asset.job_id)
        if not job or job.status != "completed":
            raise ProviderError("REFERENCE_INVALID")
    width, height = image_dimensions(asset.key)
    if profile["adapter"] == "upscale" and width * height > 5000000:
        raise ProviderError("FAL_REFERENCE_TOO_LARGE")
    if profile["adapter"] == "kling_image_audio" and (
        width < 300 or height < 300 or not 0.4 <= width / height <= 2.5
    ):
        raise ProviderError("FAL_REFERENCE_DIMENSIONS_INVALID")
    prepared["_fal_reference_pixels"] = width * height
    return prepared
