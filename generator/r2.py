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

def delete_folder(slug: str) -> None:
    """Deletes all objects within the 'thumbs/{slug}/' prefix."""
    client = get_r2_client()
    bucket_name = os.environ["CF_R2_BUCKET"]
    
    # We define the prefix based on your existing object_key structure
    # This targets "thumbs/your-slug/"
    folder_prefix = f"thumbs/{slug}/"
    
    # Using a paginator to handle buckets with more than 1000 objects
    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=folder_prefix)

    objects_found = False
    for page in pages:
        if "Contents" not in page:
            continue
        
        objects_found = True
        delete_list = [{"Key": obj["Key"]} for obj in page["Contents"]]
        
        print(f"Deleting {len(delete_list)} objects from {folder_prefix}...")
        client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": delete_list}
        )

    if not objects_found:
        print(f"No objects found with prefix: {folder_prefix}")
    else:
        print(f"Successfully deleted folder: {folder_prefix}")


if __name__ == "__main__":
    import argparse
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Cloudflare R2 Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a thumb folder by slug")
    delete_parser.add_argument("slug", type=str, help="The slug identifier of the folder to delete")
    delete_parser.add_argument(
        "--confirm", 
        action="store_true", 
        help="Confirm deletion without additional prompt"
    )

    args = parser.parse_args()

    if not r2_configured():
        print("Error: Missing R2 environment variables.")
        sys.exit(1)

    if args.command == "delete":
        if not args.confirm:
            confirmation = input(f"Are you sure you want to delete all thumbs for '{args.slug}'? (y/N): ")
            if confirmation.lower() != "y":
                print("Operation cancelled.")
                sys.exit(0)
        
        delete_folder(args.slug)
    else:
        parser.print_help()
