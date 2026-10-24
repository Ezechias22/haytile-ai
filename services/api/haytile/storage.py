"""Private local development storage or private S3-compatible object storage."""

import os
from pathlib import Path

import boto3

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
    )


def put(data, mime):
    key = uid()
    if BUCKET:
        client().put_object(
            Bucket=BUCKET,
            Key=key,
            Body=data,
            ContentType=mime,
            ServerSideEncryption="AES256",
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


def delete(key):
    if BUCKET:
        client().delete_object(Bucket=BUCKET, Key=key)
    else:
        (DIRECTORY / Path(key).name).unlink(missing_ok=True)
