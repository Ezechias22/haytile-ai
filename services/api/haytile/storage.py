"""Private local development storage or private S3-compatible object storage."""

import os
from pathlib import Path

import boto3
from botocore.config import Config

from .db import ROOT, uid

DIRECTORY = ROOT / "media"
DIRECTORY.mkdir(exist_ok=True)
BUCKET = os.environ.get("STORAGE_BUCKET")


def client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("STORAGE_ENDPOINT") or None,
        aws_access_key_id=os.environ.get("STORAGE_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.environ.get("STORAGE_SECRET_ACCESS_KEY") or None,
        region_name=os.environ.get("STORAGE_REGION", "us-east-1"),
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=60,
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


def put(data, mime):
    key = uid()
    if BUCKET:
        encryption = os.environ.get("STORAGE_SERVER_SIDE_ENCRYPTION", "AES256")
        if encryption not in ("AES256", "provider-managed"):
            raise ValueError("STORAGE_ENCRYPTION_MODE_INVALID")
        options = {"ServerSideEncryption": "AES256"} if encryption == "AES256" else {}
        client().put_object(
            Bucket=BUCKET,
            Key=key,
            Body=data,
            ContentType=mime,
            **options,
        )
    else:
        path = DIRECTORY / key
        path.write_bytes(data)
        path.chmod(0o600)
    return key


def get(key):
    if BUCKET:
        return client().get_object(Bucket=BUCKET, Key=key)["Body"].read()
    return (DIRECTORY / Path(key).name).read_bytes()


def open_range(key, start, end):
    """Open a bounded reader without allocating an entire media file."""
    if BUCKET:
        return client().get_object(Bucket=BUCKET, Key=key, Range=f"bytes={start}-{end}")["Body"]
    reader = (DIRECTORY / Path(key).name).open("rb")
    reader.seek(start)
    return reader


def delete(key):
    if BUCKET:
        client().delete_object(Bucket=BUCKET, Key=key)
    else:
        (DIRECTORY / Path(key).name).unlink(missing_ok=True)
