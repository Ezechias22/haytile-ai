"""Durable abuse counters in Firestore, using atomic document preconditions.

No account details or raw counter keys are stored. Remote failure fails closed;
it never silently falls back to a fresh local quota.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

_refresh_lock = threading.Lock()


class LimitExceeded(Exception):
    pass


class LimitUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def credentials():
    try:
        info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
        if (
            info["project_id"] != os.environ["FIREBASE_PROJECT_ID"]
            or info.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise ValueError()
        return service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/datastore"]
        )
    except (KeyError, ValueError, TypeError):
        raise LimitUnavailable() from None


@lru_cache(maxsize=1)
def client():
    return httpx.Client(
        timeout=15,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def document_url(key):
    project = os.environ.get("FIREBASE_PROJECT_ID", "")
    database = os.environ.get("FIREBASE_DATABASE_ID", "(default)")
    if not project or any(c in project + database for c in "/?#%"):
        raise LimitUnavailable()
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"https://firestore.googleapis.com/v1/projects/{project}/databases/{database}/documents/haytile_rate_limits/{digest}"


def request(method, url, **kwargs):
    try:
        cred = credentials()
        with _refresh_lock:
            if not cred.valid:

                def bounded_auth_request(*args, **options):
                    options["timeout"] = 15
                    return Request()(*args, **options)

                cred.refresh(bounded_auth_request)
        return client().request(
            method, url, headers={"Authorization": "Bearer " + cred.token}, **kwargs
        )
    except Exception:
        raise LimitUnavailable() from None


def consume(key, maximum, seconds):
    url = document_url(key)
    for _ in range(6):
        response = request("GET", url)
        instant = datetime.now(timezone.utc)
        if response.status_code == 404:
            count = 0
            reset = instant + timedelta(seconds=seconds)
            precondition = {"currentDocument.exists": "false"}
        elif response.status_code == 200:
            try:
                data = response.json()
                fields = data["fields"]
                count = int(fields["count"]["integerValue"])
                reset = datetime.fromisoformat(
                    fields["reset_at"]["timestampValue"].replace("Z", "+00:00")
                )
                if reset <= instant:
                    count, reset = 0, instant + timedelta(seconds=seconds)
                precondition = {"currentDocument.updateTime": data["updateTime"]}
            except (KeyError, ValueError, TypeError):
                raise LimitUnavailable() from None
        else:
            raise LimitUnavailable()
        if count >= maximum:
            raise LimitExceeded()
        fields = {
            "count": {"integerValue": str(count + 1)},
            "reset_at": {"timestampValue": reset.isoformat()},
        }
        response = request("PATCH", url, params=precondition, json={"fields": fields})
        if response.status_code == 200:
            return
        try:
            conflict = response.json().get("error", {}).get("status") in (
                "ABORTED",
                "FAILED_PRECONDITION",
                "ALREADY_EXISTS",
            )
        except ValueError:
            conflict = False
        if not conflict and response.status_code not in (409, 412):
            raise LimitUnavailable()
    raise LimitUnavailable()


def delete_counter(key):
    response = request("DELETE", document_url(key))
    if response.status_code not in (200, 404):
        raise LimitUnavailable()
