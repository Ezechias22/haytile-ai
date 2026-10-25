"""Private Firebase Cloud Storage, using explicit operator credentials only."""

import json
import os
from functools import lru_cache
from urllib.parse import quote
from uuid import uuid4

import httpx
from google.cloud import storage as gcs
from google.oauth2 import service_account


@lru_cache(maxsize=1)
def bucket():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    name = os.environ.get("FIREBASE_STORAGE_BUCKET")
    if not raw or not name:
        raise RuntimeError("FIREBASE_STORAGE_CONFIGURATION_MISSING")
    try:
        info = json.loads(raw)
        if (
            not isinstance(info, dict)
            or info.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise ValueError("Unexpected token endpoint")
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
        )
        # Never use inherited cloud-machine ADC or an unrelated Google identity.
        client = gcs.Client(project=info["project_id"], credentials=credentials)
        return client.bucket(name)
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("FIREBASE_STORAGE_CONFIGURATION_INVALID") from None


def blob(key):
    return bucket().blob("haytile/" + key)


def put(key, data, mime):
    blob(key).upload_from_string(data, content_type=mime, timeout=120)


def get(key):
    return blob(key).download_as_bytes(timeout=120)


def open_range(key, start, end):
    # BlobReader fetches bounded byte ranges. The API iterator caps the final byte.
    from google.api_core.exceptions import NotFound

    remote = blob(key)
    try:
        remote.reload(timeout=30)
    except NotFound:
        raise FileNotFoundError("FIREBASE_OBJECT_NOT_FOUND") from None
    reader = remote.open("rb", chunk_size=256 * 1024, timeout=60)
    try:
        reader.seek(start)
        return reader
    except Exception:
        reader.close()
        raise


def delete(key):
    from google.api_core.exceptions import NotFound

    try:
        blob(key).delete(timeout=60)
    except NotFound:
        pass


def anonymous_status(key):
    name = os.environ["FIREBASE_STORAGE_BUCKET"]
    url = (
        "https://storage.googleapis.com/"
        + quote(name, safe="")
        + "/"
        + quote("haytile/" + key, safe="/")
    )
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as response:
            return response.status_code


def probe():
    """Explicit operator test: create/read/delete only our disposable object."""
    key = "probes/" + str(uuid4())
    payload = b"haytile-private-storage-probe-v1"
    try:
        put(key, payload, "text/plain")
        if get(key) != payload:
            raise RuntimeError("FIREBASE_PROBE_READ_MISMATCH")
        reader = open_range(key, 3, 8)
        try:
            if reader.read(6) != payload[3:9]:
                raise RuntimeError("FIREBASE_PROBE_RANGE_MISMATCH")
        finally:
            reader.close()
        status = anonymous_status(key)
        if status not in (403, 404):
            raise RuntimeError("FIREBASE_PROBE_PRIVATE_ACCESS_NOT_CONFIRMED")
    finally:
        delete(key)
    return {
        "write": True,
        "read": True,
        "range": True,
        "anonymous_denied": True,
        "delete": True,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify private Firebase storage without logging credentials."
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        required=True,
        help="Create and delete one disposable object; provider usage applies.",
    )
    parser.parse_args()
    try:
        print(json.dumps({"ok": True, "checks": probe()}))
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Firebase verification failed; check backend credentials, bucket IAM and network. Details omitted to protect secrets.",
                }
            )
        )
        raise SystemExit(1) from None
