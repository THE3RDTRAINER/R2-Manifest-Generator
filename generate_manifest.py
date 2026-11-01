from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}


def generate_manifest(bucket: str, output: Path) -> int:
    load_dotenv()
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    s3_api_url = os.getenv("R2_S3_API_URL")
    access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    missing = [
        name
        for name, value in (
            ("AWS_ACCESS_KEY_ID", access_key_id),
            ("AWS_SECRET_ACCESS_KEY", secret_access_key),
        )
        if not value
    ]
    if not s3_api_url and not account_id:
        missing.insert(0, "R2_S3_API_URL or CLOUDFLARE_ACCOUNT_ID")
    if missing:
        raise ValueError(f"Missing required .env setting(s): {', '.join(missing)}")

    if s3_api_url:
        parsed_url = urlsplit(s3_api_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("R2_S3_API_URL must be a valid HTTPS URL.")
        endpoint_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    else:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name="auto",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )

    images = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            if Path(item["Key"]).suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            images.append(
                {
                    "key": item["Key"],
                    "size": item["Size"],
                    "last_modified": item["LastModified"]
                    .astimezone(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "etag": item.get("ETag"),
                }
            )

    manifest = {
        "bucket": bucket,
        "generated_at": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "images": images,
    }
    body = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    output.write_bytes(body)
    client.put_object(
        Bucket=bucket,
        Key="manifest.json",
        Body=body,
        ContentType="application/json",
    )
    return len(images)


def main() -> int:
    load_dotenv()
    bucket = os.getenv("R2_BUCKET_NAME")
    s3_api_url = os.getenv("R2_S3_API_URL")
    if not bucket and s3_api_url:
        bucket = unquote(urlsplit(s3_api_url).path.strip("/")) or None
    output = Path(os.getenv("MANIFEST_OUTPUT", "manifest.json"))

    if not bucket:
        print(
            "Set R2_BUCKET_NAME or provide the bucket path in R2_S3_API_URL.",
            file=sys.stderr,
        )
        return 1

    try:
        image_count = generate_manifest(bucket, output)
    except (BotoCoreError, ClientError, OSError, ValueError) as error:
        print(f"Failed to generate manifest: {error}", file=sys.stderr)
        return 1

    print(
        f"Wrote {image_count} image(s) to {output} and uploaded manifest.json "
        f"to bucket {bucket}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())