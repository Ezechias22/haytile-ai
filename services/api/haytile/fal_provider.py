"""Studio adapter for approved fal endpoints; reusable queue checkpoints, no fallback."""

from pathlib import Path

from . import fal_catalog, fal_client, fal_inputs
from .provider_errors import ProviderError


def resolve(value, path):
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ProviderError("PROVIDER_NO_MEDIA")
    return value


def generate(studio, model, prompt, params):
    profile = params.get("_fal_profiles", {}).get(model)
    if not profile and params.get("_fal_profile", {}).get("id") == model:
        profile = params["_fal_profile"]
    profile = profile or fal_catalog.get(model)
    if (
        not profile
        or profile["id"] != model
        or profile["studio"] != studio
        and not (profile["adapter"] == "text" and studio in ("text", "minidrama"))
    ):
        raise ProviderError("MODEL_INVALID")
    fal_catalog.validate(profile)
    if not profile.get("enabled"):
        raise ProviderError("MODEL_NOT_APPROVED")
    if not fal_client.ready():
        raise ProviderError("FAL_KEY_MISSING")
    data = fal_inputs.payload(profile, prompt, params)
    result = params.get("_resume_response") if studio != "video" else None
    if not isinstance(result, dict):
        context_callback = params.get("_operation_context_callback")
        if callable(context_callback):
            params = {
                **params,
                "_operation_callback": lambda identifier: context_callback(
                    identifier, model, studio
                ),
            }
        result = fal_client.run(profile["endpoint_id"], data, params)
    output = resolve(result, profile["output_path"])
    if profile["mime"] == "text/plain":
        if not isinstance(output, str) or not output.strip() or len(output.encode()) > 256000:
            raise ProviderError("PROVIDER_EMPTY_TEXT")
        # Existing chat marker handling is shared with Google without claiming tool use.
        if params.get("chat"):
            location_requested = (
                "[HAYTILE_REQUEST_LOCATION]" in output
                and not params.get("location")
                and params.get("_location_consent", "unknown") == "unknown"
            )
            output = output.replace("[HAYTILE_REQUEST_LOCATION]", "").strip()
            callback = params.get("_location_request_callback")
            if callable(callback):
                callback(location_requested)
            if not output:
                raise ProviderError("PROVIDER_EMPTY_TEXT")
        return output.encode(), "text/plain"
    if not isinstance(output, str):
        raise ProviderError("PROVIDER_NO_MEDIA")
    if result.get("has_nsfw_concepts") and any(result["has_nsfw_concepts"]):
        raise ProviderError("PROVIDER_CONTENT_REJECTED")
    destination = None
    if params.get("_scratch_dir") and profile["mime"].startswith(("audio/", "video/")):
        destination = Path(params["_scratch_dir"]) / "fal-result.bin"
    return fal_client.media(output, destination=destination), profile["mime"]
