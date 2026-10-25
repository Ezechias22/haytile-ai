import io

import boto3
from botocore.response import StreamingBody
from botocore.stub import Stubber

from haytile import storage


def test_s3_compatible_provider_range_and_encryption_contract(monkeypatch):
    # This protocol fixture must not inherit any developer/cloud AWS identity.
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    remote = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="fixture",
        aws_secret_access_key="fixture",
        endpoint_url="https://storage.example.test",
    )
    monkeypatch.setattr(storage, "client", lambda: remote)
    monkeypatch.setattr(storage, "BUCKET", "private-fixture")
    monkeypatch.setattr(storage, "uid", lambda: "object-fixture")
    monkeypatch.setenv("STORAGE_SERVER_SIDE_ENCRYPTION", "provider-managed")
    with Stubber(remote) as stub:
        # Supabase documents x-amz-server-side-encryption as unsupported.
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "private-fixture",
                "Key": "object-fixture",
                "Body": b"hello",
                "ContentType": "text/plain",
            },
        )
        assert storage.put(b"hello", "text/plain") == "object-fixture"
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(b"ell"), 3)},
            {"Bucket": "private-fixture", "Key": "object-fixture", "Range": "bytes=1-3"},
        )
        reader = storage.open_range("object-fixture", 1, 3)
        assert reader.read() == b"ell"
        reader.close()
        stub.assert_no_pending_responses()
