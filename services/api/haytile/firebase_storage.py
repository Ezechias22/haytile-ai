"""Private Firebase Cloud Storage, using explicit operator credentials only."""

import json
import os
from functools import lru_cache

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
        if not isinstance(info, dict) or info.get("token_uri") != "https://oauth2.googleapis.com/token":
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
