"""Cloudflare R2 upload helpers (S3-compatible via boto3)."""
from __future__ import annotations

import os
import sys
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


def _url_prefix() -> str:
    """Return the path prefix from CF_R2_PUBLIC_URL (e.g. 'myhikes', or '' if none)."""
    return urlparse(os.environ["CF_R2_PUBLIC_URL"]).path.strip("/")


def _full_key(slug: str, filename: str) -> str:
    """object_key prefixed with any path component in CF_R2_PUBLIC_URL."""
    prefix = _url_prefix()
    key = object_key(slug, filename)
    return f"{prefix}/{key}" if prefix else key


def _slug_r2_prefix(slug: str) -> str:
    """Return the R2 key prefix for all thumbnails of *slug* (with trailing slash).

    Uses the same URL-prefix derivation as _full_key so keys produced here
    are directly comparable to those produced by _full_key. The trailing slash
    prevents partial slug matches (e.g. "thumbs/abc/" won't match "thumbs/abc-extra/...").
    """
    prefix = _url_prefix()
    base = f"thumbs/{slug}/"
    return f"{prefix}/{base}" if prefix else base


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


def sync_r2_thumbnails(slug: str, photos: list) -> int:
    """Delete R2 objects for *slug* that are not in the current build.

    After uploading new/unchanged thumbnails, call this to remove any keys
    left behind by previously deleted source photos.

    Args:
        slug:   The hike slug.
        photos: Complete list of Photo objects from the current build.
                Only photos with thumb_path set are included in the expected
                set — if thumbnail generation failed, we don't delete the
                existing R2 key.

    Returns:
        Number of objects deleted.
    """
    expected: set[str] = {
        _full_key(slug, p.filename)
        for p in photos
        if p.thumb_path is not None
    }

    prefix = _slug_r2_prefix(slug)
    existing: set[str] = set(list_objects(prefix))

    orphans = existing - expected
    if not orphans:
        return 0

    client = get_r2_client()
    bucket = os.environ["CF_R2_BUCKET"]
    orphan_list = list(orphans)
    deleted = 0
    for i in range(0, len(orphan_list), 1000):  # S3 limit: 1000 keys/call
        batch = [{"Key": key} for key in orphan_list[i : i + 1000]]
        client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        deleted += len(batch)

    return deleted


def thumb_url(slug: str, filename: str) -> str:
    base = os.environ["CF_R2_PUBLIC_URL"].rstrip("/")
    return f"{base}/{object_key(slug, filename)}"


def r2_configured() -> bool:
    return all(os.environ.get(v) for v in _REQUIRED_ENV_VARS)

def list_objects(prefix: str = "") -> list[str]:
    """Return all object keys in the bucket, optionally filtered by prefix.

    Paginates transparently. Prints nothing — callers handle output.

    Args:
        prefix: Key prefix to filter by. Empty string means no filter.

    Returns:
        List of key strings matching the prefix.
    """
    client = get_r2_client()
    bucket_name = os.environ["CF_R2_BUCKET"]
    paginator = client.get_paginator("list_objects_v2")
    paginate_kwargs: dict = {"Bucket": bucket_name}
    if prefix:
        paginate_kwargs["Prefix"] = prefix
    keys: list[str] = []
    for page in paginator.paginate(**paginate_kwargs):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


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
        keys = list_objects(args.prefix)
        print(f"Listing bucket: {os.environ['CF_R2_BUCKET']!r}, prefix: {args.prefix!r}")
        for key in keys:
            print(key)
        print(f"\n{len(keys)} object(s) found.")
    elif args.command == "delete":
        delete_folder(args.prefix)
    else:
        parser.print_help()
