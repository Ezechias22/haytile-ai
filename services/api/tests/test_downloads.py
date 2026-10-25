import pytest

from haytile import storage
from haytile.db import Session, User

from .conftest import register


def test_private_media_range_seek_head_and_limits(client, monkeypatch):
    _, headers = register(client)
    content = "abcdefghij"
    response = client.post(
        "/v1/assets/text", headers=headers, json={"title": "Range fixture", "text": content}
    )
    assert response.status_code == 201
    asset = response.json()
    link = client.get(f"/v1/assets/{asset['id']}/link", headers=headers).json()["path"]
    # The download path must not use the full-file loader.
    monkeypatch.setattr(storage, "get", lambda key: pytest.fail("Unbounded file read"))
    for byte_header, expected, content_range in [
        ("bytes=2-5", b"cdef", "bytes 2-5/10"),
        ("bytes=7-", b"hij", "bytes 7-9/10"),
        ("bytes=-3", b"hij", "bytes 7-9/10"),
        ("bytes=0-99", b"abcdefghij", "bytes 0-9/10"),
    ]:
        result = client.get(link, headers={"Range": byte_header})
        assert result.status_code == 206
        assert result.content == expected
        assert result.headers["content-range"] == content_range
        assert int(result.headers["content-length"]) == len(expected)
    for invalid in ["bytes=11-", "bytes=5-2", "bytes=-0", "bytes=", "bytes=0-1,4-5"]:
        result = client.get(link, headers={"Range": invalid})
        assert result.status_code == 416 and result.headers["content-range"] == "bytes */10"
    result = client.head(link)
    assert result.status_code == 200 and result.content == b""
    assert result.headers["content-length"] == "10"
    assert (
        client.get(link, headers={"Range": "bytes=2-3", "If-Range": '"old"'}).content
        == content.encode()
    )
    assert client.get(link.replace("signature=", "signature=invalid")).status_code == 403


def test_operations_is_admin_only_and_does_not_expose_secrets(client, monkeypatch):
    monkeypatch.setenv("HAYTILE_SIGNING_KEY", "private-fixture-must-never-appear" * 2)
    assert client.get("/v1/admin/operations").status_code == 401
    user, headers = register(client)
    assert client.get("/v1/admin/operations", headers=headers).status_code == 403
    with Session.begin() as db:
        db.get(User, user["id"]).role = "admin"
    response = client.get("/v1/admin/operations", headers=headers)
    assert response.status_code == 200
    assert response.json()["configuration_checks"]["explicit_signing_key"] is True
    assert "private-fixture" not in response.text
