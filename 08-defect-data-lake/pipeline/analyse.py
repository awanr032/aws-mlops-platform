"""Answer reliability questions with SQL, and measure why curated Parquet matters.

Part 1: runs every query in analysis/*.sql against the curated table.
Part 2: asks the SAME question of the raw text table and of the curated Parquet table and
        compares how much data each had to read (what Athena charges for).
"""

from __future__ import annotations

import glob
import os
import sys

import athena

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, "..", "analysis")

RAW_QUESTION = """
SELECT trim(split_part(compdesc, ':', 1)) AS component_group, count(*) AS complaints
FROM {database}.complaints_raw
WHERE substr(trim(ldate), 1, 4) = '{year}'
GROUP BY 1 ORDER BY 2 DESC LIMIT 5
"""
CURATED_QUESTION = """
SELECT component_group, count(*) AS complaints
FROM {database}.complaints_elt
WHERE received_year = {year}
GROUP BY 1 ORDER BY 2 DESC LIMIT 5
"""


def load_queries(database: str, year: int) -> list[tuple[str, str]]:
    """[(title, sql)] from analysis/*.sql; the title is the first comment line."""
    queries = []
    for path in sorted(glob.glob(os.path.join(ANALYSIS, "*.sql"))):
        text = open(path).read()
        title = text.splitlines()[0].lstrip("- ").replace("{year}", str(year))
        queries.append((title, text.format(database=database, year=year)))
    return queries


def comparison_summary(raw: dict, curated: dict) -> str:
    ratio = raw["scanned_bytes"] / max(curated["scanned_bytes"], 1)
    saving = 100 * (1 - curated["scanned_bytes"] / max(raw["scanned_bytes"], 1))
    return (f"  raw text table : read {athena.human_bytes(raw['scanned_bytes']):>9}  in {raw['wall_ms'] / 1000:5.1f} s\n"
            f"  curated Parquet: read {athena.human_bytes(curated['scanned_bytes']):>9}  in {curated['wall_ms'] / 1000:5.1f} s\n"
            f"  → {ratio:,.0f}x less data read ({saving:.1f}% cheaper) for the same answer")


def main() -> int:
    database = os.environ["DATABASE"]
    year = int(os.environ.get("ANALYSIS_YEAR", "2024"))

    print(f"PART 1: reliability questions (curated table, year {year})")
    total_scanned = 0
    for title, sql in load_queries(database, year):
        result = athena.run(sql)
        total_scanned += result["scanned_bytes"]
        print(f"\n## {title}")
        print(athena.table(result))
        print(f"   (read {athena.human_bytes(result['scanned_bytes'])}, {result['wall_ms'] / 1000:.1f} s)")
    print(f"\nAll questions together read {athena.human_bytes(total_scanned)} "
          f"≈ ${total_scanned / 1e12 * athena.PRICE_PER_TB:.5f}")

    print(f"\nPART 2: same question, raw text vs curated Parquet "
          f"('top 5 component groups received in {year}')")
    raw = athena.run(RAW_QUESTION.format(database=database, year=year))
    curated = athena.run(CURATED_QUESTION.format(database=database, year=year))
    print("raw answer:\n" + athena.table(raw))
    print("curated answer:\n" + athena.table(curated))
    print(comparison_summary(raw, curated))
    return 0


if __name__ == "__main__":
    sys.exit(main())
