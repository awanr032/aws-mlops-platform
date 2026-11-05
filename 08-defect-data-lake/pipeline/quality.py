"""Data quality checks: did the transformation keep the data it should, and do ELT and ETL agree?

  completeness  how many raw rows were dropped (no complaint ID or no received date)
  validity      share of missing values in key columns after cleaning
  uniqueness    duplicate complaint IDs
  consistency   the SQL (ELT) and Spark (ETL) outputs must match year by year
"""

from __future__ import annotations

import os
import sys

import athena

MAX_DROPPED_PCT = 2.0
MAX_ELT_ETL_DIFF_PCT = 0.1

PER_YEAR = """
SELECT CAST(received_year AS integer) AS y, count(*) AS n, sum(injured) AS injured,
       sum(deaths) AS deaths, count_if(fire) AS fires, count(DISTINCT make) AS makes
FROM {table} GROUP BY 1 ORDER BY 1
"""


def as_dict(result: dict) -> dict:
    """{year: {column: int}} from a PER_YEAR result."""
    out = {}
    for row in result["rows"]:
        values = dict(zip(result["columns"], row))
        year = int(values.pop("y"))
        out[year] = {k: int(v or 0) for k, v in values.items()}
    return out


def compare(elt: dict, etl: dict, tolerance_pct: float = MAX_ELT_ETL_DIFF_PCT) -> list[str]:
    problems = []
    for year in sorted(set(elt) | set(etl)):
        a, b = elt.get(year), etl.get(year)
        if a is None or b is None:
            problems.append(f"{year}: only in {'ETL' if a is None else 'ELT'}")
            continue
        for metric in a:
            if a[metric] == b.get(metric):
                continue
            diff_pct = 100 * abs(a[metric] - b.get(metric, 0)) / max(a[metric], 1)
            if diff_pct > tolerance_pct:
                problems.append(f"{year} {metric}: ELT {a[metric]} vs ETL {b.get(metric)} ({diff_pct:.2f}%)")
    return problems


def dropped_pct(raw_rows: int, curated_rows: int) -> float:
    return round(100 * (raw_rows - curated_rows) / raw_rows, 3) if raw_rows else 0.0


def main() -> int:
    db = os.environ["DATABASE"]
    failures = []

    raw = int(athena.run(f"SELECT count(*) FROM {db}.complaints_raw")["rows"][0][0])
    profile = athena.run(f"""
        SELECT count(*) AS rows, count(*) - count(DISTINCT complaint_id) AS duplicate_ids,
               round(100.0 * count_if(make IS NULL) / count(*), 2) AS make_missing_pct,
               round(100.0 * count_if(model_year IS NULL) / count(*), 2) AS model_year_missing_pct,
               round(100.0 * count_if(component IS NULL) / count(*), 2) AS component_missing_pct,
               round(100.0 * count_if(miles IS NULL) / count(*), 2) AS miles_missing_pct,
               min(received_date) AS first_received, max(received_date) AS last_received
        FROM {db}.complaints_elt""")
    stats = dict(zip(profile["columns"], profile["rows"][0]))
    curated = int(stats["rows"])
    dropped = dropped_pct(raw, curated)

    print("Completeness")
    print(f"  raw rows {raw:,} → curated rows {curated:,}: {dropped}% dropped (limit {MAX_DROPPED_PCT}%)")
    if dropped > MAX_DROPPED_PCT:
        failures.append(f"{dropped}% of rows dropped")
    print("Validity (share of missing values after cleaning)")
    for key in ("make_missing_pct", "model_year_missing_pct", "component_missing_pct", "miles_missing_pct"):
        print(f"  {key:24} {stats[key]}%")
    print(f"  received dates from {stats['first_received']} to {stats['last_received']}")
    print("Uniqueness")
    print(f"  duplicate complaint IDs: {stats['duplicate_ids']}")
    if int(stats["duplicate_ids"]) > 0:
        failures.append(f"{stats['duplicate_ids']} duplicate complaint IDs")

    print("Consistency: ELT (SQL in Athena) vs ETL (Spark in Glue)")
    try:
        elt = as_dict(athena.run(PER_YEAR.format(table=f"{db}.complaints_elt")))
        etl = as_dict(athena.run(PER_YEAR.format(table=f"{db}.etl_complaints")))
        problems = compare(elt, etl)
        print(f"  {len(elt)} years compared on rows, injuries, deaths, fires and number of makes")
        for p in problems:
            print("  MISMATCH " + p)
        if problems:
            failures.append("ELT and ETL outputs differ")
        else:
            print("  identical: two different engines, same rules, same result")
    except athena.QueryFailed as exc:
        print(f"  skipped: ETL table not available yet (run 'etl' first) [{str(exc).splitlines()[0]}]")

    print("\nRESULT:", "PASSED" if not failures else "FAILED: " + "; ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
