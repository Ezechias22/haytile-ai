"""Archive legacy live SQL metadata to the same private Firebase project.

Never generates AI or downloads media bytes. Short-lived operator sessions are
used only for owner-scoped export GETs, and removed in finally. No passwords,
tokens, signed URLs or private content are printed or written to local files.
Run with explicit Firebase backend credentials injected into the process.
"""

import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from haytile import accounts as store
from haytile import firebase_storage, records
from haytile.db import now
from haytile.security import hash_token

ORIGIN = "https://haytile-ai.onrender.com"


def date(value):
    parsed = datetime.fromisoformat(value) if value else now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def object_key(url):
    import os

    parsed = urlsplit(url)
    bucket = os.environ["FIREBASE_STORAGE_BUCKET"]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "storage.googleapis.com"
        or parsed.port not in (None, 443)
    ):
        raise RuntimeError("Unexpected private media origin; archive stopped.")
    prefix = "/" + bucket + "/haytile/"
    path = unquote(parsed.path)
    if not path.startswith(prefix) or not re.fullmatch(
        r"[A-Za-z0-9-]{36}", path[len(prefix) :]
    ):
        raise RuntimeError("Unexpected media namespace; archive stopped.")
    return path[len(prefix) :]


def save(kind, data):
    for _ in range(5):
        old = store.read(kind, data["id"])
        if old:
            if old[0].get("user_id") != data["user_id"]:
                raise RuntimeError("Metadata owner mismatch; archive stopped.")
            if old[0].get("payload") == records.serial(data):
                return False
        try:
            store.commit(
                [
                    store.update_write(
                        kind,
                        data["id"],
                        records.document(data, kind, "legacy-migration"),
                        version=old[1] if old else None,
                        create=not bool(old),
                    )
                ]
            )
            check = store.read(kind, data["id"])
            if not check or check[0]["payload"] != records.serial(data):
                raise RuntimeError("Archive read-back mismatch.")
            return True
        except store.Conflict:
            continue
    raise RuntimeError("Concurrent metadata changes; archive stopped.")


def main():
    counts = {
        "users": 0,
        "jobs": 0,
        "assets": 0,
        "projects": 0,
        "active_jobs": 0,
        "changed": 0,
    }
    offset = 0
    with httpx.Client(timeout=55, follow_redirects=False) as client:
        while True:
            users, total = store.directory(offset=offset)
            if not users:
                break
            for account in users:
                raw = secrets.token_urlsafe(32)
                digest = hash_token(raw)
                if not store.session(account, digest, now() + timedelta(minutes=10)):
                    raise RuntimeError("Account changed during archival; retry safely.")
                headers = {"Authorization": "Bearer " + raw}
                try:
                    response = client.get(ORIGIN + "/api/v1/me/export", headers=headers)
                    response.raise_for_status()
                    if len(response.content) > 32 * 1024 * 1024:
                        raise RuntimeError(
                            "Metadata exceeds the bounded legacy exporter."
                        )
                    exported = response.json()
                    if exported["profile"]["id"] != account["id"]:
                        raise RuntimeError("Export owner mismatch.")
                    active = [
                        j
                        for j in exported["jobs"]
                        if j["status"] not in ("completed", "failed")
                    ]
                    counts["active_jobs"] += len(active)
                    if active:
                        raise RuntimeError(
                            "Active jobs remain. No deployment is safe yet; wait for them to finish."
                        )
                    p = client.get(ORIGIN + "/api/v1/projects", headers=headers)
                    p.raise_for_status()
                    projects = p.json()
                    final_ids = {x["document"].get("final_asset_id") for x in projects}
                    legacy_assets = exported["assets"]
                    for job in exported["jobs"]:
                        params = dict(job["params"])
                        final = next(
                            (
                                a
                                for a in legacy_assets
                                if a.get("job_id") == job["id"] and a["id"] in final_ids
                            ),
                            None,
                        )
                        if not final:
                            final = next(
                                (
                                    a
                                    for a in legacy_assets
                                    if a.get("job_id") == job["id"]
                                    and not a["title"].startswith(
                                        ("[Reference] ", "[Scene] ")
                                    )
                                ),
                                None,
                            )
                        if final:
                            params["result_asset_id"] = final["id"]
                        data = {
                            k: job[k]
                            for k in (
                                "id",
                                "title",
                                "studio",
                                "prompt",
                                "status",
                                "progress",
                                "error",
                                "credits",
                                "attempt",
                            )
                        }
                        data.update(
                            user_id=account["id"],
                            params=params,
                            idempotency_key="legacy-migrated-" + job["id"],
                            lease_until=None,
                            created_at=date(job["created_at"]),
                            updated_at=date(job.get("updated_at") or job["created_at"]),
                        )
                        counts["changed"] += save("jobs", data)
                        counts["jobs"] += 1
                    for asset in legacy_assets:
                        response = client.get(
                            ORIGIN + "/api/v1/assets/" + asset["id"] + "/link",
                            headers=headers,
                        )
                        response.raise_for_status()
                        link = response.json()
                        key = object_key(link.get("media_url") or link["download_url"])
                        blob = firebase_storage.blob(key)
                        blob.reload(timeout=30)
                        if blob.size != asset["size"]:
                            raise RuntimeError("Media size mismatch; archive stopped.")
                        data = {
                            k: asset[k]
                            for k in ("id", "title", "mime", "size", "text", "job_id")
                        }
                        data.update(
                            user_id=account["id"],
                            key=key,
                            created_at=date(asset["created_at"]),
                        )
                        counts["changed"] += save("assets", data)
                        counts["assets"] += 1
                    for project in projects:
                        data = {
                            k: project[k]
                            for k in ("id", "title", "document", "version")
                        }
                        data.update(
                            user_id=account["id"],
                            created_at=date(project["created_at"]),
                        )
                        counts["changed"] += save("projects", data)
                        counts["projects"] += 1
                    counts["users"] += 1
                finally:
                    store.logout(digest)
            offset += len(users)
            if offset >= total:
                break
    Path(".local").mkdir(exist_ok=True)
    Path(".local/legacy-metadata-archive.json").write_text(
        json.dumps({**counts, "verified": True, "timestamp": now().isoformat()})
    )
    print(json.dumps({**counts, "verified": True, "paid_generation_requests": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — suppress private export and credential details
        print(
            "Legacy archive did not complete. No deployment was started; private details omitted."
        )
        raise SystemExit(1) from None
