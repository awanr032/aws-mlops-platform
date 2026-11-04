"""Indexer Lambda: runs when a manual is uploaded to or deleted from s3://<bucket>/manuals/.

It rebuilds the whole index from every manual (simple and always consistent; fine for
hundreds of manuals). Each build goes to its own folder, index/<build_id>/, and manifest.json
is written LAST and points at it, so the question Lambda never sees a half-written index.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid

import boto3

import bedrock
from chunking import chunk_markdown, embedding_text
from store import CHUNKS_FILE, INDEX_FILE, VectorStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MANUALS_PREFIX = "manuals/"
INDEX_PREFIX = "index/"
MANIFEST_KEY = "index/manifest.json"
SUFFIXES = (".md", ".txt")


def build(manuals: dict, embed_fn, build_id: str) -> tuple[VectorStore, dict]:
    """manuals: {s3_key: (text, etag)}. Returns the store and its manifest. Pure apart from embed_fn."""
    chunks, per_manual = [], {}
    for key in sorted(manuals):
        text, _etag = manuals[key]
        source = os.path.splitext(os.path.basename(key))[0]
        found = chunk_markdown(text, source)
        per_manual[key] = len(found)
        chunks.extend(found)
    if not chunks:
        raise ValueError("the manuals contain no text")
    for n, chunk in enumerate(chunks, start=1):
        chunk["id"] = f"{chunk['source']}#{n}"
    vectors = [embed_fn(embedding_text(c)) for c in chunks]
    store = VectorStore.build(vectors, chunks)
    manifest = {
        "build_id": build_id,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "embedding_model": bedrock.EMBED_MODEL_ID,
        "dimensions": store.dimensions,
        "chunks": len(chunks),
        "chunks_per_manual": per_manual,
        "manuals": {key: etag for key, (_text, etag) in manuals.items()},
    }
    return store, manifest


def list_manuals(s3, bucket: str) -> dict:
    """{key: etag} for every manual in S3. The ETag is a fingerprint of the file's content."""
    found = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=MANUALS_PREFIX):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(SUFFIXES):
                found[obj["Key"]] = obj["ETag"].strip('"')
    return found


def read_manuals(s3, bucket: str) -> dict:
    return {key: (s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"), etag)
            for key, etag in list_manuals(s3, bucket).items()}


def _old_builds(s3, bucket: str, keep: set) -> list[str]:
    old = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=INDEX_PREFIX):
        for obj in page.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) == 3 and parts[1] not in keep:
                old.append(obj["Key"])
    return old


def handler(event, context):
    started = time.perf_counter()
    bucket = os.environ["BUCKET"]
    s3 = boto3.client("s3")
    triggers = [r["s3"]["object"]["key"] for r in event.get("Records", []) if "s3" in r]

    try:
        previous = json.loads(s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())["build_id"]
    except s3.exceptions.NoSuchKey:
        previous = None

    manuals = read_manuals(s3, bucket)
    if not manuals:
        s3.delete_object(Bucket=bucket, Key=MANIFEST_KEY)
        logger.info(json.dumps({"event": "index_removed", "reason": "no manuals"}))
        return {"chunks": 0}

    build_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    store, manifest = build(manuals, bedrock.embed, build_id)
    with tempfile.TemporaryDirectory() as folder:
        store.save(folder)
        for name in (INDEX_FILE, CHUNKS_FILE):
            s3.upload_file(os.path.join(folder, name), bucket, f"{INDEX_PREFIX}{build_id}/{name}")
    # Uploading several manuals starts several runs at once. Only a run that indexed the manuals
    # as they are NOW may publish; an older run steps aside for the newer one.
    if list_manuals(s3, bucket) != manifest["manuals"]:
        logger.info(json.dumps({"event": "index_superseded", "build_id": build_id}))
        return {"superseded": build_id}
    s3.put_object(Bucket=bucket, Key=MANIFEST_KEY, Body=json.dumps(manifest, indent=2).encode(),
                  ContentType="application/json")

    # Keep this build and the previous one (a question Lambda may still be using it); delete the rest.
    old = _old_builds(s3, bucket, {build_id, previous})
    for start in range(0, len(old), 1000):
        s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in old[start:start + 1000]]})

    summary = {"event": "index_built", "build_id": build_id, "manuals": len(manuals),
               "chunks": manifest["chunks"], "triggered_by": triggers[:5],
               "deleted_old_files": len(old), "ms": round((time.perf_counter() - started) * 1000)}
    logger.info(json.dumps(summary))
    return summary
