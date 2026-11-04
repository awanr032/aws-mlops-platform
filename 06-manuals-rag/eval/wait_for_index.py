"""Wait until the indexer Lambda has indexed exactly the manuals now in S3.

Uploading manuals triggers the indexer through an S3 event, so the workflow can't call it
directly; it watches index/manifest.json until its list of manuals (and their ETags, i.e.
content fingerprints) matches what is in s3://<bucket>/manuals/.
"""

from __future__ import annotations

import json
import os
import sys
import time

import boto3

TIMEOUT_SECONDS = 300


def current_manuals(s3, bucket: str) -> dict:
    found = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="manuals/"):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith((".md", ".txt")):
                found[obj["Key"]] = obj["ETag"].strip('"')
    return found


def main() -> int:
    bucket = os.environ["BUCKET"]
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-2"))
    expected = current_manuals(s3, bucket)
    print(f"Waiting for an index of {len(expected)} manuals: {sorted(expected)}")
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            manifest = json.loads(s3.get_object(Bucket=bucket, Key="index/manifest.json")["Body"].read())
            if manifest.get("manuals") == expected:
                print(json.dumps(manifest, indent=2))
                return 0
            print(f"  index {manifest.get('build_id')} covers {len(manifest.get('manuals', {}))} manuals; waiting")
        except s3.exceptions.NoSuchKey:
            print("  no index yet; waiting")
        time.sleep(10)
    print("::error::The index was not rebuilt in time. Check the indexer's logs in CloudWatch: "
          "/aws/lambda/manuals-rag-indexer")
    return 1


if __name__ == "__main__":
    sys.exit(main())
