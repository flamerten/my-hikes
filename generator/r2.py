"""Cloudflare R2 upload helpers (S3-compatible via boto3)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

_REQUIRED_ENV_VARS = (
    "CF_R2_BUCKET",
    "CF_R2_ENDPOINT_URL",
    "CF_R2_ACCESS_KEY_ID",
    "CF_R2_SECRET_ACCESS_KEY",
    "CF_R2_PUBLIC_URL",
)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["CF_R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"],
    )


def object_key(slug: str, filename: str) -> str:
    return f"thumbs/{slug}/{filename}"


def _full_key(slug: str, filename: str) -> str:
    """object_key prefixed with any path component in CF_R2_PUBLIC_URL."""
    prefix = urlparse(os.environ["CF_R2_PUBLIC_URL"]).path.strip("/")
    key = object_key(slug, filename)
    return f"{prefix}/{key}" if prefix else key


def upload_thumbnail(local_path: Path, slug: str, filename: str) -> None:
    """Upload a thumbnail to R2, skipping if the object already exists."""
    client = get_r2_client()
    bucket = os.environ["CF_R2_BUCKET"]
    key = _full_key(slug, filename)

    try:
        client.head_object(Bucket=bucket, Key=key)
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "404":
            raise

    client.upload_file(
        str(local_path),
        bucket,
        key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )


def thumb_url(slug: str, filename: str) -> str:
    base = os.environ["CF_R2_PUBLIC_URL"].rstrip("/")
    return f"{base}/{object_key(slug, filename)}"


def r2_configured() -> bool:
    return all(os.environ.get(v) for v in _REQUIRED_ENV_VARS)
