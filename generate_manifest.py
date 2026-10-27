import argparse
from datetime import datetime, timezone
import json
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def generate_manifest(bucket, account_id, manifest_key):
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        region_name="auto",
    )

    objects = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            if item["Key"] == manifest_key:
                continue

            objects.append(
                {
                    "key": item["Key"],
                    "size": item["Size"],
                    "last_modified": item["LastModified"].astimezone(
                        timezone.utc
                    ).isoformat().replace("+00:00", "Z"),
                    "etag": item.get("ETag"),
                    "storage_class": item.get("StorageClass", "STANDARD"),
                }
            )

    manifest = {
        "bucket": bucket,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "objects": objects,
    }
    body = json.dumps(manifest, indent=2).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=body,
        ContentType="application/json",
    )
    return len(objects)


def main():
    parser = argparse.ArgumentParser(
        description="Generate and upload a JSON manifest of a Cloudflare R2 bucket."
    )
    parser.add_argument("--bucket", required=True, help="R2 bucket name")
    parser.add_argument(
        "--account-id",
        default=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
        help="Cloudflare account ID (or set CLOUDFLARE_ACCOUNT_ID)",
    )
    parser.add_argument(
        "--manifest-key",
        default="manifest.json",
        help="Object key for the uploaded manifest (default: manifest.json)",
    )
    args = parser.parse_args()

    if not args.account_id:
        parser.error("--account-id is required unless CLOUDFLARE_ACCOUNT_ID is set")

    try:
        object_count = generate_manifest(
            args.bucket, args.account_id, args.manifest_key
        )
    except (BotoCoreError, ClientError) as error:
        print(f"Failed to generate or upload manifest: {error}", file=sys.stderr)
        return 1

    print(
        f"Uploaded {args.manifest_key} to bucket {args.bucket} "
        f"with {object_count} objects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())