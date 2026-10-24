"""Provider boundary. No model IDs are guessed or enabled automatically."""

import base64
import io
import os
import re
import wave

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta"


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
            r = client.request(method, BASE + path, headers=headers(), json=payload)
        if r.status_code >= 400:
            raise ProviderError(f"PROVIDER_HTTP_{r.status_code}")
        return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("PROVIDER_NETWORK_OR_RESPONSE") from exc


def discover():
    result, token, seen = [], None, set()
    while True:
        path = "/models?pageSize=1000"
        # httpx URL construction handles query escaping when supplied via QueryParams.
        if token:
            from urllib.parse import quote

            path = "/models?pageSize=1000&pageToken=" + quote(token, safe="")
        data = request("GET", path)
        for m in data.get("models", []):
            result.append(
                {
                    k: m.get(k)
                    for k in ("name", "displayName", "supportedGenerationMethods")
                }
            )
        token = data.get("nextPageToken")
        if not token:
            return result
        if token in seen:
            raise ProviderError("PROVIDER_PAGINATION")
        seen.add(token)


def generate(studio, model, prompt, params):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", model):
        raise ProviderError("MODEL_INVALID")
    if studio in ("video", "music"):
        payload = {"model": model, "input": prompt, "store": False, "background": False}
        if studio == "video":
            payload["response_format"] = {
                "type": "video",
                "aspect_ratio": params.get("aspect", "16:9"),
                "resolution": "720p",
            }
            if params.get("_reference_data"):
                payload["input"] = [
                    {
                        "type": "image",
                        "mime_type": params["_reference_mime"],
                        "data": params["_reference_data"],
                    },
                    {"type": "text", "text": prompt},
                ]
        result = request("POST", "/interactions", payload)
        parts = [
            p
            for s in result.get("steps", [])
            if s.get("type") == "model_output"
            for p in s.get("content", [])
        ]
        for p in parts:
            if p.get("type") == ("video" if studio == "video" else "audio") and p.get(
                "data"
            ):
                return base64.b64decode(p["data"], validate=True), p.get(
                    "mime_type", "video/mp4" if studio == "video" else "audio/mpeg"
                )
        raise ProviderError("PROVIDER_NO_AUDIO")
    config = {"maxOutputTokens": 4096}
    if studio == "image":
        config.update(
            {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": params.get("aspect", "1:1")},
            }
        )
    elif studio == "voice":
        config = {"responseModalities": ["AUDIO"]}
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
        text = "\n".join(
            p["text"] for p in output if "text" in p and not p.get("thought")
        )
        if not text.strip():
            raise ProviderError("PROVIDER_EMPTY_TEXT")
        return text.encode(), "text/plain"
    for part in output:
        item = part.get("inlineData")
        if not item:
            continue
        mime = item.get("mimeType", "")
        data = base64.b64decode(item["data"], validate=True)
        if studio == "image" and mime.startswith("image/"):
            return data, mime
        if studio == "voice" and mime.startswith("audio/"):
            if "L16" in mime or "pcm" in mime:
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
