"""fal metadata + queue transport. Credentials never leave the two API hosts.

Only queue submission creates work. Status/result/catalog/pricing are metadata
reads. Never automatically resubmit an uncertain or rejected generation.
"""

import json
import os
import re
import time
from urllib.parse import urljoin, urlsplit

import httpx

from .provider_errors import ProviderError

PLATFORM = "https://api.fal.ai/v1"
QUEUE = "https://queue.fal.run"
MAX_RESULT_BYTES = 256 * 1024 * 1024
ENDPOINT = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/[A-Za-z0-9._-]+)*")
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,150}")


def ready():
    return bool((os.environ.get("FAL_KEY") or os.environ.get("Fal_key", "")).strip())


def endpoint(value):
    if not isinstance(value, str) or len(value) > 250 or not ENDPOINT.fullmatch(value):
        raise ProviderError("MODEL_INVALID")
    return value


def request(method, path, payload=None, *, platform=False, public=False, params=None):
    if not path.startswith("/") or path.startswith("//") or ".." in path:
        raise ProviderError("PROVIDER_OPERATION_INVALID")
    key = (os.environ.get("FAL_KEY") or os.environ.get("Fal_key", "")).strip()
    if not key and not public:
        raise ProviderError("FAL_KEY_MISSING")
    headers = {"Authorization": "Key " + key} if key else {}
    if method == "POST" and not platform:
        headers.update(
            {
                "X-Fal-No-Retry": "1",
                "x-app-fal-disable-fallback": "true",
                "X-Fal-Store-IO": "0",
                "X-Fal-Object-Lifecycle-Preference": '{"expiration_duration_seconds":86400}',
            }
        )
    try:
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            response = client.request(
                method,
                (PLATFORM if platform else QUEUE) + path,
                json=payload,
                params=params,
                headers=headers,
            )
        if response.status_code >= 400:
            try:
                details = response.json()
                error = details.get("error") if isinstance(details.get("error"), dict) else {}
                message = details.get("detail", details.get("message", error.get("message", "")))
                if not isinstance(message, str):
                    message = json.dumps(message, ensure_ascii=False)
            except (ValueError, AttributeError):
                message = ""
            if key:
                message = message.replace(key, "[redacted]")
            message = re.sub(r"AIza[A-Za-z0-9_-]+", "[redacted]", message)[:1000]
            code = {
                401: "PROVIDER_ACCESS_DENIED",
                402: "PROVIDER_BALANCE_REQUIRED",
                403: "PROVIDER_ACCESS_DENIED",
                404: "PROVIDER_MODEL_UNAVAILABLE",
                429: "PROVIDER_QUOTA_EXCEEDED",
            }.get(response.status_code, "PROVIDER_HTTP_" + str(response.status_code))
            if response.status_code in (400, 422):
                code = (
                    "PROVIDER_CONTENT_REJECTED"
                    if re.search(
                        r"content_policy|content.{0,30}(?:block|policy)|(?:unsafe|nsfw|prohibited)|input blocked",
                        message,
                        re.I,
                    )
                    else "PROVIDER_REQUEST_REJECTED"
                )
            raise ProviderError(code, message or None, str(response.status_code))
        value = response.json()
        if not isinstance(value, dict):
            raise ProviderError("PROVIDER_NETWORK_OR_RESPONSE")
        return value
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("PROVIDER_NETWORK_OR_RESPONSE") from exc


def catalog(query="", category="", cursor="", identifier="", expand=False):
    params = {"limit": 10 if expand else 25}
    for key, value in (
        ("q", query),
        ("category", category),
        ("cursor", cursor),
        ("endpoint_id", identifier),
    ):
        if value:
            params[key] = value
    if expand:
        params["expand"] = "openapi-3.0"
    return request("GET", "/models", platform=True, public=True, params=params)


def pricing(identifier):
    return request(
        "GET", "/models/pricing", platform=True, params={"endpoint_id": endpoint(identifier)}
    )


def operation(identifier, request_id):
    endpoint(identifier)
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ProviderError("PROVIDER_OPERATION_INVALID")
    return "/" + "/".join(identifier.split("/")[:2]) + "/requests/" + request_id


def run(identifier, payload, params):
    identifier = endpoint(identifier)
    request_id = params.get("_resume_operation_id")
    if not request_id:
        callback = params.get("_submission_callback")
        if callable(callback):
            callback()
        submitted = request("POST", "/" + identifier, payload)
        request_id = submitted.get("request_id")
        operation(identifier, request_id)  # Never follow arbitrary status/result URLs.
        callback = params.get("_operation_callback")
        if callable(callback):
            callback(request_id)
    path = operation(identifier, request_id)
    deadline = time.monotonic() + int(os.environ.get("HAYTILE_PROVIDER_POLL_SECONDS", "600"))
    while True:
        state = request("GET", path + "/status", params={"logs": "0"})
        if state.get("status") == "COMPLETED":
            result = request("GET", path)
            callback = params.get("_response_callback")
            if callable(callback):
                callback(result)
            return result
        if state.get("status") not in ("IN_QUEUE", "IN_PROGRESS"):
            raise ProviderError("PROVIDER_OPERATION_FAILED")
        if time.monotonic() >= deadline:
            raise ProviderError("PROVIDER_OPERATION_PENDING")
        time.sleep(2)


def media(url, destination=None):
    """Bounded downloads from fal's documented media hosts, with no API auth."""
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as client:
            for _ in range(4):
                parsed = urlsplit(url)
                host = parsed.hostname or ""
                if (
                    parsed.scheme != "https"
                    or parsed.port not in (None, 443)
                    or parsed.username
                    or parsed.password
                    or not (
                        host == "fal.media"
                        or host.endswith(".fal.media")
                        or host == "storage.googleapis.com"
                        and parsed.path.startswith("/falserverless/")
                    )
                ):
                    raise ProviderError("PROVIDER_MEDIA_DESTINATION_REJECTED")
                with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200:
                        raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED")
                    if int(response.headers.get("content-length", "0")) > MAX_RESULT_BYTES:
                        raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
                    if destination is not None:
                        count = 0
                        with destination.open("wb") as target:
                            for chunk in response.iter_bytes():
                                count += len(chunk)
                                if count > MAX_RESULT_BYTES:
                                    raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
                                target.write(chunk)
                        if count == 0:
                            raise ProviderError("PROVIDER_NO_MEDIA")
                        return destination
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > min(MAX_RESULT_BYTES, 30 * 1024 * 1024):
                            raise ProviderError("PROVIDER_MEDIA_TOO_LARGE")
                    if not data:
                        raise ProviderError("PROVIDER_NO_MEDIA")
                    return bytes(data)
            raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED")
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("PROVIDER_MEDIA_DOWNLOAD_FAILED") from exc
