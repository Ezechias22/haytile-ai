import io

import pytest

from haytile import firebase_storage, storage

from .conftest import register


def test_firebase_private_library_range_delete_without_local_media(client, monkeypatch):
    objects = {}
    opened = []

    class Blob:
        def __init__(self, key):
            self.key = key

        def upload_from_string(self, data, content_type, timeout):
            objects[self.key] = data

        def download_as_bytes(self, timeout):
            return objects[self.key]

        def reload(self, timeout):
            assert self.key in objects

        def open(self, mode, chunk_size, timeout):
            opened.append((mode, chunk_size))
            return io.BytesIO(objects[self.key])

        def delete(self, timeout):
            objects.pop(self.key)

    class Bucket:
        def blob(self, key):
            assert key.startswith("haytile/")
            return Blob(key)

    monkeypatch.setenv("STORAGE_PROVIDER", "firebase")
    monkeypatch.setattr(firebase_storage, "bucket", lambda: Bucket())
    _, headers = register(client)
    client.cookies.clear()
    response = client.post(
        "/v1/assets/text",
        headers=headers,
        json={"title": "Firebase protocol fixture", "text": "abcdefghij"},
    )
    assert response.status_code == 201
    asset = response.json()
    assert len(objects) == 1
    key = next(iter(objects)).removeprefix("haytile/")
    assert not (storage.DIRECTORY / key).exists()
    assert storage.get(key) == b"abcdefghij"
    assert client.get("/v1/health").json()["storage"] == "firebase"
    assert client.get("/v1/assets/" + asset["id"] + "/link").status_code == 401
    link = client.get("/v1/assets/" + asset["id"] + "/link", headers=headers).json()[
        "path"
    ]
    response = client.get(link, headers={"range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"cdef"
    assert opened == [("rb", 256 * 1024)]
    assert (
        client.delete("/v1/assets/" + asset["id"], headers=headers).status_code == 200
    )
    assert objects == {}


def test_firebase_configuration_does_not_fall_back_to_machine_google_identity(
    monkeypatch,
):
    firebase_storage.bucket.cache_clear()
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("FIREBASE_STORAGE_BUCKET", "fixture-bucket")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/must-not-be-read.json")
    with pytest.raises(RuntimeError, match="FIREBASE_STORAGE_CONFIGURATION_MISSING"):
        firebase_storage.bucket()
    monkeypatch.setenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON", '{"token_uri":"https://untrusted.example"}'
    )
    with pytest.raises(RuntimeError, match="FIREBASE_STORAGE_CONFIGURATION_INVALID"):
        firebase_storage.bucket()
    firebase_storage.bucket.cache_clear()
