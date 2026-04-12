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
    # R2 endpoint must be just scheme+host — strip any path component (bucket name)
    # that may have been appended to CF_R2_ENDPOINT_URL by mistake.
    parsed = urlparse(os.environ["CF_R2_ENDPOINT_URL"])
    endpoint = f"{parsed.scheme}://{parsed.netloc}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
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

def list_objects(prefix: str = "") -> None:
    """List all objects in the bucket, optionally filtered by prefix."""
    client = get_r2_client()
    bucket_name = os.environ["CF_R2_BUCKET"]
    print(f"Listing bucket: {bucket_name!r}, prefix: {prefix!r}")
    paginator = client.get_paginator("list_objects_v2")
    paginate_kwargs: dict = {"Bucket": bucket_name}
    if prefix:
        paginate_kwargs["Prefix"] = prefix
    count = 0
    for page in paginator.paginate(**paginate_kwargs):
        for obj in page.get("Contents", []):
            print(obj["Key"])
            count += 1
    print(f"\n{count} object(s) found.")


def delete_folder(prefix: str) -> None:
    """Delete all objects whose key starts with prefix."""
    client = get_r2_client()
    bucket_name = os.environ["CF_R2_BUCKET"]
    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    objects_found = False
    for page in pages:
        if "Contents" not in page:
            continue
        
        objects_found = True
        delete_list = [{"Key": obj["Key"]} for obj in page["Contents"]]

        print(f"Deleting {len(delete_list)} objects under {prefix!r}...")
        confirmation = input("Are you sure? (y/N): ")
        if confirmation.lower() != "y":
            print("Operation cancelled.")
            sys.exit(0)

        client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": delete_list}
        )

    if not objects_found:
        print(f"No objects found with prefix: {prefix!r}")
    else:
        print(f"Done.")


if __name__ == "__main__":
    import argparse
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Cloudflare R2 Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List all objects in the bucket")
    list_parser.add_argument("--prefix", type=str, default="", help="Optional prefix to filter by")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete all objects matching a key prefix")
    delete_parser.add_argument("prefix", type=str, help="Key prefix to delete (e.g. 'myhikes/thumbs/my-hike/')")

    args = parser.parse_args()

    if not r2_configured():
        print("Error: Missing R2 environment variables.")
        sys.exit(1)

    if args.command == "list":
        list_objects(args.prefix)
    elif args.command == "delete":
        delete_folder(args.prefix)
    else:
        parser.print_help()
