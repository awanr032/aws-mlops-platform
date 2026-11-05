"""ELT: transform inside the lake with SQL (Athena CREATE TABLE AS SELECT).

Re-runnable: drops the old table and its files first, because CTAS refuses to write into a
folder that already has data.
"""

from __future__ import annotations

import os
import sys

import athena

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(HERE, "..", "elt", "complaints_elt.sql")
PREFIX = "curated/elt/complaints/"


def build_sql(database: str, bucket: str) -> str:
    with open(SQL_FILE) as f:
        return f.read().format(database=database, bucket=bucket)


def empty_prefix(s3, bucket: str, prefix: str) -> int:
    deleted = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
            deleted += len(keys)
    return deleted


def main() -> int:
    import boto3

    database, bucket = os.environ["DATABASE"], os.environ["BUCKET"]
    print("1. Removing the previous ELT output (if any)")
    athena.run(f"DROP TABLE IF EXISTS {database}.complaints_elt")
    print(f"   deleted {empty_prefix(boto3.client('s3'), bucket, PREFIX)} old files")

    print("2. CREATE TABLE AS SELECT: raw text → typed, cleaned, partitioned Parquet")
    result = athena.run(build_sql(database, bucket))
    print(f"   done in {result['wall_ms'] / 1000:.0f} s; read {athena.human_bytes(result['scanned_bytes'])} "
          f"of raw data (≈ ${result['cost_usd']:.4f})")

    print("3. Rows per received year in the new table")
    print(athena.table(athena.run(
        f"SELECT received_year, count(*) AS complaints FROM {database}.complaints_elt "
        f"GROUP BY 1 ORDER BY 1"), limit=50))
    return 0


if __name__ == "__main__":
    sys.exit(main())
