"""Google provider boundary with bounded media downloads and operation polling."""

import base64
import io
import os
import re
import time
import wave
from urllib.parse import quote, urlsplit

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_MEDIA_BYTES = 256 * 1024 * 1024


class ProviderError(Exception):
    pass


def headers():
    key = os.environ.get("HAYTILE_GEMINI_API_KEY")
    if not key:
        raise ProviderError("PROVIDER_KEY_MISSING")
    return {"x-goog-api-key": key}


def request(method, path, payload=None, timeout=240):
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(method, BASE + path, headers=headers(), json=payload)
        if response.status_code >= 400:
            status = None
            try:
                status = response.json().get("error", {}).get("status")
            except (ValueError, AttributeError):
                pass
            known = {
                "RESOURCE_EXHAUSTED": "PROVIDER_QUOTA_EXCEEDED",
                "PERMISSION_DENIED": "PROVIDER_ACCESS_DENIED",
                "NOT_FOUND": "PROVIDER_MODEL_UNAVAILABLE",
                "UNAUTHENTICATED": "PROVIDER_AUTH_FAILED",
            }
            raise ProviderError(known.get(status, f"PROVIDER_HTTP_{response.status_code}"))
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("PROVIDER_NETWORK_OR_RESPONSE") from exc


def discover():
    result = []
    token = None
    seen = set()
    while True:
        path = "/models?pageSize=1000" + ("&pageToken=" + quote(token, safe="") if token else "")
        data = request("GET", path)
        for model in data.get("models", []):
            result.append(
                {k: model.get(k) for k in ("name", "displayName", "supportedGenerationMethods")}
            )
        token = data.get("nextPageToken")
        if not token:
            return result
        if not isinstance(token, str) or token in seen:
            raise ProviderError("PROVIDER_PAGINATION")
        seen.add(token)


def media_bytes(part):
    data = part.get("data")
    if data:
        if not isinstance(data, str) or len(data) > MAX_MEDIA_BYTES * 4 // 3 + 8:
            raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
        try:
            return base64.b64decode(data, validate=True)
        except (ValueError, TypeError) as exc:
            raise ProviderError("PROVIDER_INVALID_MEDIA") from exc
    uri = part.get("uri")
    if not isinstance(uri, str):
        raise ProviderError("PROVIDER_NO_MEDIA")
    file_id = None
    if re.fullmatch(r"files/[A-Za-z0-9_-]+", uri):
        file_id = uri.split("/")[-1]
    else:
        parsed = urlsplit(uri)
        try:
            valid_port = parsed.port in (None, 443)
        except ValueError:
            valid_port = False
        if (
            parsed.scheme != "https"
            or parsed.hostname != "generativelanguage.googleapis.com"
            or not valid_port
            or parsed.username
            or parsed.password
        ):
            raise ProviderError("PROVIDER_MEDIA_DESTINATION_REJECTED")
        match = re.fullmatch(r"/v1beta/files/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            file_id = match.group(1)
    if file_id:
        deadline = time.monotonic() + int(os.environ.get("HAYTILE_PROVIDER_POLL_SECONDS", "600"))
        while True:
            metadata = request("GET", "/files/" + file_id, timeout=60)
            state = metadata.get("state")
            if isinstance(state, dict):
                state = state.get("name")
            if state == "FAILED":
                raise ProviderError("PROVIDER_MEDIA_PROCESSING_FAILED")
            if state != "PROCESSING":
                break
            if time.monotonic() >= deadline:
                raise ProviderError("PROVIDER_OPERATION_PENDING")
            time.sleep(2)
        uri = BASE + "/files/" + file_id + ":download?alt=media"
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as client:
            for _ in range(4):
                parsed = urlsplit(uri)
                try:
                    valid_port = parsed.port in (None, 443)
                except ValueError:
                    valid_port = False
                host = parsed.hostname or ""
                allowed = host in (
                    "generativelanguage.googleapis.com",
                    "storage.googleapis.com",
                ) or host.endswith(".googleusercontent.com")
                if (
                    parsed.scheme != "https"
                    or not allowed
                    or not valid_port
                    or parsed.username
                    or parsed.password
                ):
                    raise ProviderError("PROVIDER_MEDIA_DESTINATION_REJECTED")
                auth = headers() if host == "generativelanguage.googleapis.com" else {}
                with client.stream("GET", uri, headers=auth) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        uri = response.headers.get("location", "")
                        continue
                    if response.status_code != 200:
                        raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED")
                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_MEDIA_BYTES:
                        raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
                    result = bytearray()
                    for chunk in response.iter_bytes():
                        result.extend(chunk)
                        if len(result) > MAX_MEDIA_BYTES:
                            raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
                    return bytes(result)
            raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED")
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED") from exc


def interaction_parts(result):
    parts = []
    for step in result.get("steps", []):
        if step.get("type") == "model_output":
            parts.extend(step.get("content", []))
    parts.extend(result.get("outputs", []))
    return parts


def wait_interaction(result, params):
    deadline = time.monotonic() + int(os.environ.get("HAYTILE_PROVIDER_POLL_SECONDS", "600"))
    identifier = result.get("id")
    if identifier:
        callback = params.get("_operation_callback")
        if callable(callback):
            callback(identifier)
    while result.get("status") in ("in_progress", "queued", "pending", "processing"):
        if not identifier or not re.fullmatch(r"[A-Za-z0-9._-]{1,300}", identifier):
            raise ProviderError("PROVIDER_OPERATION_INVALID")
        if time.monotonic() >= deadline:
            raise ProviderError("PROVIDER_OPERATION_PENDING")
        time.sleep(2)
        result = request("GET", "/interactions/" + quote(identifier, safe=""), timeout=60)
    if result.get("status") in ("failed", "cancelled", "canceled", "requires_action"):
        raise ProviderError("PROVIDER_OPERATION_FAILED")
    return result


def generate(studio, model, prompt, params):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", model):
        raise ProviderError("MODEL_INVALID")
    interaction_voice = studio == "voice" and model.startswith("gemini-3.8-")
    if studio in ("video", "music") or interaction_voice:
        resume = params.get("_resume_operation_id")
        if resume:
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,300}", resume):
                raise ProviderError("PROVIDER_OPERATION_INVALID")
            result = request("GET", "/interactions/" + quote(resume, safe=""))
        else:
            payload = {
                "model": model,
                "input": prompt,
                "store": True,
                "background": False,
            }
            if interaction_voice:
                payload["input"] = [
                    {"type": "user_input", "content": [{"type": "text", "text": prompt}]}
                ]
                payload["response_format"] = {"type": "audio"}
                payload["generation_config"] = {"speech_config": [{"voice": "Kore"}]}
            if studio == "video":
                payload["response_format"] = {
                    "type": "video",
                    "aspect_ratio": params.get("aspect", "16:9"),
                    "resolution": "720p",
                    "delivery": "uri",
                }
                references = params.get("_reference_images", [])
                if references:
                    payload["input"] = [
                        {"type": "image", "mime_type": ref["mime_type"], "data": ref["data"]}
                        for ref in references
                    ] + [{"type": "text", "text": prompt}]
                elif params.get("_reference_data"):
                    payload["input"] = [
                        {
                            "type": "image",
                            "mime_type": params["_reference_mime"],
                            "data": params["_reference_data"],
                        },
                        {"type": "text", "text": prompt},
                    ]
            result = request("POST", "/interactions", payload)
        result = wait_interaction(result, params)
        for part in interaction_parts(result):
            if part.get("type") == ("video" if studio == "video" else "audio") and (
                part.get("data") or part.get("uri")
            ):
                return media_bytes(part), part.get(
                    "mime_type",
                    "video/mp4"
                    if studio == "video"
                    else "audio/wav"
                    if interaction_voice
                    else "audio/mpeg",
                )
        raise ProviderError("PROVIDER_NO_VIDEO" if studio == "video" else "PROVIDER_NO_AUDIO")
    config = {"maxOutputTokens": min(int(params.get("_max_output_tokens", 2048)), 8192)}
    if studio == "image":
        config.update(
            {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": params.get("aspect", "1:1")},
            }
        )
    elif studio == "voice":
        config = {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
        }
    parts = [{"text": prompt}]
    if params.get("_reference_data"):
        parts.append(
            {
                "inlineData": {
                    "mimeType": params["_reference_mime"],
                    "data": params["_reference_data"],
                }
            }
        )
    response = request(
        "POST",
        f"/models/{model}:generateContent",
        {"contents": [{"role": "user", "parts": parts}], "generationConfig": config},
    )
    candidates = response.get("candidates", [])
    if not candidates or candidates[0].get("finishReason") in (
        "SAFETY",
        "RECITATION",
        "PROHIBITED_CONTENT",
    ):
        raise ProviderError("PROVIDER_REFUSED_OR_EMPTY")
    output = candidates[0].get("content", {}).get("parts", [])
    if studio in ("text", "minidrama"):
        text = "\n".join(p["text"] for p in output if "text" in p and not p.get("thought"))
        if not text.strip():
            raise ProviderError("PROVIDER_EMPTY_TEXT")
        return text.encode(), "text/plain"
    for part in output:
        item = part.get("inlineData")
        if not item:
            continue
        mime = item.get("mimeType", "")
        data = media_bytes({"data": item.get("data")})
        if studio == "image" and mime.startswith("image/"):
            return data, mime
        if studio == "voice" and mime.startswith("audio/"):
            if "l16" in mime.lower() or "pcm" in mime.lower():
                match = re.search(r"rate=(\d+)", mime)
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(int(match.group(1)) if match else 24000)
                    audio.writeframes(data)
                return buffer.getvalue(), "audio/wav"
            return data, mime
    raise ProviderError("PROVIDER_NO_MEDIA")
