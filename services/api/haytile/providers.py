"""Google provider boundary with bounded media downloads and operation polling."""

import base64
import io
import os
import re
import time
import wave
from urllib.parse import quote, urlsplit

import httpx

from .music import direction_prompt, target_seconds
from .voice_choices import VOCALS, VOICES

BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_MEDIA_BYTES = 256 * 1024 * 1024


class ProviderError(Exception):
    def __init__(self, code, public_message=None, provider_status=None):
        super().__init__(code)
        self.public_message = public_message
        self.provider_status = provider_status


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
            message = None
            try:
                error = response.json().get("error", {})
                status = error.get("status")
                message = error.get("message")
            except (ValueError, AttributeError):
                pass
            known = {
                "RESOURCE_EXHAUSTED": "PROVIDER_QUOTA_EXCEEDED",
                "PERMISSION_DENIED": "PROVIDER_ACCESS_DENIED",
                "NOT_FOUND": "PROVIDER_MODEL_UNAVAILABLE",
                "UNAUTHENTICATED": "PROVIDER_AUTH_FAILED",
            }
            if isinstance(message, str):
                key = os.environ.get("HAYTILE_GEMINI_API_KEY", "")
                if key:
                    message = message.replace(key, "[redacted]")
                message = re.sub(r"AIza[A-Za-z0-9_-]+", "[redacted]", message)[:1000]
            else:
                message = None
            code = known.get(status, f"PROVIDER_HTTP_{response.status_code}")
            if response.status_code == 400:
                code = "PROVIDER_REQUEST_REJECTED"
                if message and re.search(
                    r"content.{0,40}(?:violat|policy)|(?:block|reject).{0,30}(?:content|prompt)|responsible.?ai",
                    message,
                    re.I,
                ):
                    code = "PROVIDER_CONTENT_REJECTED"
            raise ProviderError(code, message, status)
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
    voice = params.get("voice_name", "Kore")
    if studio == "voice" and voice not in VOICES:
        raise ProviderError("VOICE_INVALID")
    if studio == "music":
        try:
            musical_direction = direction_prompt(params)
        except ValueError as exc:
            raise ProviderError("MUSIC_DIRECTION_INVALID") from exc
        duration = params.get(
            "duration", params.get("_music_target_seconds", target_seconds(prompt, model, params))
        )
        if duration is not None:
            if type(duration) is not int or not 30 <= duration <= 300:
                raise ProviderError("MUSIC_DURATION_INVALID")
            if model == "lyria-3-clip-preview" and duration != 30:
                raise ProviderError("MUSIC_CLIP_DURATION_INVALID")
            prompt = (
                f"Target song duration: {duration} seconds. Compose a complete song with "
                "a natural finished outro. Follow the supplied song structure; only invent "
                "verses, choruses or a bridge when the user provided a creative brief rather than lyrics. "
                "Plan the musical structure across the requested duration; do not abruptly "
                "cut off the vocals or ending. This duration is approximate: prioritize singing "
                "all supplied lyrics exactly once over forcing the estimated time. Do not omit, "
                "invent or repeat lines to fill time. Keep instrumental openings and breaks short "
                "when many lyrics are supplied, and leave room to finish the final sung line and outro.\n\n" + prompt
            )
        prompt = (
            "Interpret the song in its actual artistic and educational context. "
            "A non-graphic prevention or awareness song may discuss illness, violence, "
            "abuse, discrimination or other social problems without endorsing harm. "
            "Do not reject an educational purpose merely because a sensitive topic is named. "
            "Do not introduce explicit sexual content or harmful advocacy. Preserve the user's "
            "supplied lyrics; never silently censor, replace or invent lines.\n\n" + prompt
        )
        direction = params.get("vocal_style", "auto")
        if direction not in VOCALS:
            raise ProviderError("VOCAL_STYLE_INVALID")
        if VOCALS[direction]:
            prompt = VOCALS[direction] + " Preserve the requested language and lyrics.\n\n" + prompt
        prompt = musical_direction + "SONG CONTENT / CREATIVE BRIEF:\n" + prompt
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
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ]
                payload["response_format"] = {"type": "audio"}
                payload["generation_config"] = {"speech_config": [{"voice": voice}]}
                if params.get("_max_output_tokens"):
                    payload["generation_config"]["max_output_tokens"] = params["_max_output_tokens"]
            if studio == "video":
                payload["generation_config"] = {"max_output_tokens": 57920}
                payload["response_format"] = {
                    "type": "video",
                    "aspect_ratio": params.get("aspect", "16:9"),
                    "resolution": "720p",
                    "delivery": "uri",
                }
                references = params.get("_reference_images", [])
                if references:
                    payload["input"] = [
                        {
                            "type": "image",
                            "mime_type": ref["mime_type"],
                            "data": ref["data"],
                        }
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
        parts = interaction_parts(result)
        # Google's output_audio convenience accessor selects the LAST audio block.
        # Match that documented selection rather than returning early on the first block.
        if studio == "music":
            parts = reversed(parts)
        for part in parts:
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
            "maxOutputTokens": min(int(params.get("_max_output_tokens", 32768)), 32768),
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        }
    if studio == "image" and params.get("_image_size") and not model.startswith("gemini-2.5-"):
        config["imageConfig"]["imageSize"] = params["_image_size"]
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
    payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
    if studio == "text" and "_chat_contents" in params:
        from .chat import system_for

        payload["systemInstruction"] = {
            "parts": [{"text": system_for(prompt, params.get("voice_conversation") is True)}]
        }
        payload["contents"] = params["_chat_contents"] + payload["contents"]
    if studio == "text" and params.get("chat") is True:
        if params.get("_chat_materialized") is not None:
            payload["contents"] = params["_chat_materialized"]
        location = params.get("location")
        if location:
            payload["contents"][-1]["parts"].append(
                {
                    "text": f"Device-reported location authorized by the user: latitude {location['latitude']:.6f}, longitude {location['longitude']:.6f}. Reported accuracy: {location.get('accuracy_m', 'unknown')} meters. Captured at: {location.get('captured_at', 'unknown')}. Treat this as the last reported fix, not a guarantee of exact or current position. Never ask for location permission again when already authorized. If the fix is stale or uncertain, explain this and ask whether the user is still in that area."
                }
            )
        consent = params.get("_location_consent", "unknown")
        if consent in ("enabled", "disabled"):
            payload["systemInstruction"]["parts"].append(
                {
                    "text": "Location preference is remembered: "
                    + consent
                    + ". Do not request location permission or emit the application location marker again. If permission is disabled or position unavailable, ask for a city/address instead; the user can change their saved preference in the location control."
                }
            )
        if params.get("chat") is True:
            payload["tools"] = [{"googleSearch": {}}]
            payload["systemInstruction"]["parts"].append(
                {
                    "text": "Decide automatically whether web search is needed: use it for current, uncertain, time-sensitive or local facts, but not for greetings, creative writing or stable facts you can answer confidently. Cite sources for researched claims. Do not include the complete text of private attached documents in search queries; only search general non-sensitive terms relevant to the question. If no web sources are returned, say clearly that current facts were not verified."
                }
            )
    response = params.get("_resume_response") if studio == "text" else None
    if response is None:
        response = request("POST", f"/models/{model}:generateContent", payload)
        checkpoint = params.get("_response_callback")
        if studio == "text" and callable(checkpoint):
            checkpoint(response)
    candidates = response.get("candidates", [])
    block = (response.get("promptFeedback") or {}).get("blockReason")
    finish = candidates[0].get("finishReason") if candidates else None
    if block or finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT"):
        raise ProviderError(
            "PROVIDER_CONTENT_REJECTED", "Provider safety decision: " + str(block or finish)
        )
    if not candidates:
        raise ProviderError("PROVIDER_EMPTY_TEXT")
    if studio == "text" and params.get("chat") is True:
        from .chat_tools import grounding

        callback = params.get("_grounding_callback")
        if callable(callback):
            callback(grounding(candidates[0].get("groundingMetadata", {})))
    output = (candidates[0].get("content") or {}).get("parts") or []
    if studio == "text" and params.get("chat") is True:
        from .chat_tools import cite_parts

        output = cite_parts(output, candidates[0].get("groundingMetadata", {}))
    if studio in ("text", "minidrama"):
        text = "\n".join(p["text"] for p in output if "text" in p and not p.get("thought"))
        location_requested = (
            "[HAYTILE_REQUEST_LOCATION]" in text
            and not params.get("location")
            and params.get("_location_consent", "unknown") == "unknown"
        )
        if params.get("chat") is True:
            text = text.replace("[HAYTILE_REQUEST_LOCATION]", "").strip()
        if studio == "text" and params.get("chat") is True:
            callback = params.get("_location_request_callback")
            if callable(callback):
                callback(location_requested)
        if location_requested and not text:
            text = {
                "ht": "Ou ka otorize lokalizasyon an oswa ekri vil ou pou mwen ede w.",
                "en": "You can authorize location or enter your city so I can help.",
                "fr": "Vous pouvez autoriser la localisation ou indiquer votre ville pour que je vous aide.",
                "pt-BR": "Você pode autorizar a localização ou informar sua cidade para que eu ajude.",
                "es": "Puede autorizar la ubicación o indicar su ciudad para que le ayude.",
                "ar": "يمكنك السماح بالموقع أو كتابة مدينتك حتى أساعدك.",
                "zh-Hans": "您可以允许获取位置，或输入城市，以便我提供帮助。",
                "id": "Anda dapat mengizinkan lokasi atau memasukkan kota agar saya dapat membantu.",
                "sw": "Unaweza kuruhusu mahali au kuandika mji wako ili nikusaidie.",
            }.get(
                params.get("language", "en"),
                "You can authorize location or enter your city so I can help.",
            )
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
