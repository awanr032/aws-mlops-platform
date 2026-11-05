"""EXTRACT + LOAD: download NHTSA complaint files and land them in the RAW zone of the lake.

  1. Find which 5-year complaint files exist (COMPLAINTS_RECEIVED_2020-2024.zip, ...)
  2. Download each zip and unpack its text file
  3. Convert to UTF-8 (the source mixes encodings; Athena and Spark expect UTF-8) and count
     fields per line; that is the only change. Raw stays otherwise exactly as published.
  4. Upload to s3://<bucket>/raw/complaints/ and write a manifest (what, when, from where, how much)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter

BASE_URL = "https://static.nhtsa.gov/odi/ffdd/cmpl/"
# Tried in order; for each start year the first file that exists is used. NHTSA names the
# current, incomplete chunk differently over time, so several spellings are tried.
DEFAULT_CHUNKS = "2020-2024,2025-2029,2025-2026,2025-2025"
EXPECTED_FIELDS = 51
USER_AGENT = "aws-mlops-platform-learning-project"


def chunk_url(chunk: str) -> str:
    return f"{BASE_URL}COMPLAINTS_RECEIVED_{chunk}.zip"


def exists(url: str) -> int | None:
    """Size in bytes if the URL exists, else None. Tries a HEAD request, then a 1-byte download
    (some servers refuse HEAD)."""
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as r:
            return int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
    except urllib.error.URLError:
        pass
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"})
        with urllib.request.urlopen(request, timeout=30) as r:
            total = (r.headers.get("Content-Range") or "").rpartition("/")[2]
            return int(total) if total.isdigit() else int(r.headers.get("Content-Length") or 0)
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def choose_chunks(candidates: list[str], probe=exists) -> list[tuple[str, int]]:
    """For each start year, the first candidate that exists: [(chunk, size_bytes)]."""
    chosen, covered = [], set()
    for chunk in candidates:
        start = chunk.split("-")[0]
        if start in covered:
            continue
        size = probe(chunk_url(chunk))
        print(f"  {chunk_url(chunk)}: {'found, %.0f MB' % (size / 1e6) if size is not None else 'not found'}")
        if size is not None:
            chosen.append((chunk, size))
            covered.add(start)
    return chosen


def decode(line: bytes) -> tuple[str, bool]:
    """UTF-8 if valid, otherwise Windows-1252 (common in older US government files)."""
    try:
        return line.decode("utf-8"), False
    except UnicodeDecodeError:
        return line.decode("cp1252", errors="replace"), True


def normalise(source, target) -> dict:
    """Copy lines from a binary stream to a UTF-8 text stream; return statistics."""
    fields, converted, lines = Counter(), 0, 0
    for raw_line in source:
        line, was_converted = decode(raw_line.rstrip(b"\r\n"))
        if not line.strip():
            continue
        target.write(line + "\n")
        lines += 1
        converted += was_converted
        fields[line.count("\t") + 1] += 1
    return {"lines": lines, "lines_converted_from_cp1252": converted,
            "fields_per_line": {str(k): v for k, v in sorted(fields.items())}}


def download(url: str, path: str) -> str:
    sha = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as r, open(path, "wb") as f:
        while block := r.read(1 << 20):
            f.write(block)
            sha.update(block)
    return sha.hexdigest()


def main() -> int:
    import boto3

    bucket = os.environ["BUCKET"]
    s3 = boto3.client("s3")
    candidates = os.environ.get("CHUNKS", DEFAULT_CHUNKS).split(",")
    print("1. Looking for NHTSA complaint files")
    chunks = choose_chunks(candidates)
    if not chunks:
        print("::error::No complaint files found. Check https://www.nhtsa.gov/nhtsa-datasets-and-apis "
              "for the current names and set CHUNKS.")
        return 1

    manifest = {"downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": []}
    for chunk, _size in chunks:
        url = chunk_url(chunk)
        with tempfile.TemporaryDirectory() as tmp:
            print(f"2. Downloading {url}")
            zip_path = os.path.join(tmp, "data.zip")
            sha = download(url, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                member = next(n for n in z.namelist() if n.lower().endswith((".txt", ".lst")))
                out_path = os.path.join(tmp, f"COMPLAINTS_RECEIVED_{chunk}.txt")
                print(f"3. Unpacking {member} and converting to UTF-8")
                with z.open(member) as source, open(out_path, "w", encoding="utf-8") as target:
                    stats = normalise(source, target)
            key = f"raw/complaints/COMPLAINTS_RECEIVED_{chunk}.txt"
            size = os.path.getsize(out_path)
            print(f"4. Uploading {size / 1e6:.0f} MB to s3://{bucket}/{key}")
            s3.upload_file(out_path, bucket, key)
        unexpected = sum(v for k, v in stats["fields_per_line"].items() if int(k) not in (49, EXPECTED_FIELDS))
        entry = {"source_url": url, "zip_sha256": sha, "s3_key": key, "bytes": size, **stats,
                 "lines_with_unexpected_field_count": unexpected}
        manifest["files"].append(entry)
        print("   " + json.dumps(entry))

    key = f"raw/_manifests/ingest-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.json"
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(manifest, indent=2).encode(),
                  ContentType="application/json")
    total = sum(f["lines"] for f in manifest["files"])
    print(f"\nLanded {total:,} complaint rows in the raw zone. Manifest: s3://{bucket}/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
