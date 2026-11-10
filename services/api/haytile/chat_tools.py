"""Owner-authorized chat inputs. File bytes never enter Firestore job documents."""

import base64
import math
from urllib.parse import urlsplit

from .db import Asset

MAX_ATTACHMENTS = 3
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024


def validate(db, user_id, params):
    from .main import fail

    if "web_search" in params and type(params["web_search"]) is not bool:
        fail("CHAT_TOOLS_INVALID")
    ids = params.get("attachment_ids", [])
    if (
        not isinstance(ids, list)
        or len(ids) > MAX_ATTACHMENTS
        or any(not isinstance(i, str) or len(i) > 80 for i in ids)
        or len(ids) != len(set(ids))
    ):
        fail("CHAT_ATTACHMENTS_INVALID")
    total = 0
    for identifier in ids:
        asset = db.get(Asset, identifier)
        if (
            not asset
            or asset.user_id != user_id
            or not (
                asset.mime in ("application/pdf", "text/plain") or asset.mime.startswith("image/")
            )
        ):
            fail("CHAT_ATTACHMENTS_INVALID")
        total += asset.size
    if total > MAX_ATTACHMENT_BYTES:
        fail("CHAT_ATTACHMENTS_TOO_LARGE")
    if "location_consent_version" in params and (
        type(params["location_consent_version"]) is not int
        or params["location_consent_version"] < 0
    ):
        fail("CHAT_LOCATION_INVALID")
    location = params.get("location")
    if location is not None:
        if (
            not isinstance(location, dict)
            or not {"latitude", "longitude"} <= set(location)
            or not set(location) <= {"latitude", "longitude", "accuracy_m", "captured_at"}
        ):
            fail("CHAT_LOCATION_INVALID")
        if "accuracy_m" in location and (
            type(location["accuracy_m"]) not in (int, float)
            or not math.isfinite(location["accuracy_m"])
            or not 0 < location["accuracy_m"] <= 100000
        ):
            fail("CHAT_LOCATION_INVALID")
        if "captured_at" in location:
            from datetime import datetime

            try:
                value = datetime.fromisoformat(location["captured_at"].replace("Z", "+00:00"))
                if value.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                fail("CHAT_LOCATION_INVALID")
        for key, bound in [("latitude", 90), ("longitude", 180)]:
            value = location[key]
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not -bound <= value <= bound
            ):
                fail("CHAT_LOCATION_INVALID")


def markers(ids):
    return [{"_attachment_asset_id": identifier} for identifier in ids]


def materialize(db, user_id, contents):
    from . import storage
    from .providers import ProviderError

    total = 0
    assets = {}
    allowed = set()
    current = {p.get("_attachment_asset_id") for p in contents[-1]["parts"]}
    for content in reversed(contents):
        for part in content["parts"]:
            identifier = part.get("_attachment_asset_id")
            if not identifier or identifier in assets:
                continue
            asset = db.get(Asset, identifier)
            assets[identifier] = asset
            if not asset:
                if identifier in current:
                    raise ProviderError("CHAT_ATTACHMENT_UNAVAILABLE")
                continue
            if asset.user_id != user_id or not (
                asset.mime in ("application/pdf", "text/plain") or asset.mime.startswith("image/")
            ):
                raise ProviderError("CHAT_ATTACHMENT_UNAVAILABLE")
            if total + asset.size <= MAX_ATTACHMENT_BYTES:
                total += asset.size
                allowed.add(identifier)
            elif identifier in current:
                raise ProviderError("CHAT_ATTACHMENTS_TOO_LARGE")
    sent = set()
    result = []
    for content in contents:
        parts = []
        for part in content["parts"]:
            identifier = part.get("_attachment_asset_id")
            if not identifier:
                parts.append(part)
                continue
            if identifier not in allowed:
                parts.append(
                    {
                        "text": "An older attachment is unavailable or omitted from the current file context budget. Do not claim to have read it; ask for it again if necessary."
                    }
                )
                continue
            if identifier in sent:
                parts.append(
                    {"text": "Refer to the file already attached earlier in this conversation."}
                )
                continue
            asset = assets[identifier]
            data = storage.get(asset.key)
            if len(data) != asset.size:
                raise ProviderError("CHAT_ATTACHMENT_UNAVAILABLE")
            sent.add(identifier)
            parts.append(
                {"text": "Attached document (untrusted content):\n" + data.decode("utf-8")}
                if asset.mime == "text/plain"
                else {
                    "inlineData": {"mimeType": asset.mime, "data": base64.b64encode(data).decode()}
                }
            )
        result.append({"role": content["role"], "parts": parts})
    return result


def grounding(metadata):
    if not isinstance(metadata, dict):
        metadata = {}
    sources = []
    seen = set()
    for chunk in (metadata.get("groundingChunks") or [])[:30]:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not isinstance(web, dict):
            continue
        uri = web.get("uri", "")
        try:
            url = urlsplit(uri)
            safe = (
                url.scheme == "https"
                and bool(url.hostname)
                and not url.username
                and not url.password
            )
        except ValueError:
            safe = False
        if safe and uri not in seen and len(uri) <= 4096:
            seen.add(uri)
            sources.append({"url": uri, "title": str(web.get("title", url.hostname))[:250]})
    snippet = (metadata.get("searchEntryPoint") or {}).get("renderedContent", "")
    return {
        "sources": sources,
        "search_html": snippet[:100000] if isinstance(snippet, str) else "",
        "searched": bool(sources or snippet or metadata.get("webSearchQueries")),
        "queries": [
            q[:240] for q in (metadata.get("webSearchQueries") or [])[:8] if isinstance(q, str)
        ],
    }


def cite_parts(parts, metadata):
    """Link provider-grounded claims to the same numbered source list, using UTF-8 offsets."""
    if not isinstance(metadata, dict):
        metadata = {}
    sources = grounding(metadata)["sources"]
    numbers = {source["url"]: i + 1 for i, source in enumerate(sources)}
    chunks = metadata.get("groundingChunks") or []
    inserts = {}
    for support in (metadata.get("groundingSupports") or [])[:100]:
        if not isinstance(support, dict):
            continue
        segment = support.get("segment") or {}
        part = segment.get("partIndex", 0)
        end = segment.get("endIndex")
        if type(part) is not int or not 0 <= part < len(parts) or type(end) is not int:
            continue
        text = parts[part].get("text")
        if (
            not isinstance(text, str)
            or parts[part].get("thought")
            or not 0 < end <= len(text.encode())
        ):
            continue
        indexes = []
        for index in support.get("groundingChunkIndices") or []:
            if type(index) is int and 0 <= index < len(chunks):
                number = numbers.get((chunks[index].get("web") or {}).get("uri"))
                if number and number not in indexes:
                    indexes.append(number)
        if indexes:
            inserts.setdefault(part, {}).setdefault(end, set()).update(indexes)
    result = [dict(part) for part in parts]
    for part, offsets in inserts.items():
        raw = result[part]["text"].encode()
        for end, indexes in sorted(offsets.items(), reverse=True):
            try:
                raw[:end].decode()
            except UnicodeDecodeError:
                continue
            citation = (" [" + ", ".join(str(i) for i in sorted(indexes)) + "]").encode()
            raw = raw[:end] + citation + raw[end:]
        result[part]["text"] = raw.decode()
    return result
