import os

import analyse
import elt
import etl
import quality

YEARS = {2023: {"n": 1000, "injured": 40, "deaths": 2, "fires": 12, "makes": 55},
         2024: {"n": 1200, "injured": 50, "deaths": 1, "fires": 15, "makes": 57}}


def test_identical_outputs_have_no_problems():
    assert quality.compare(YEARS, {y: dict(v) for y, v in YEARS.items()}) == []


def test_differences_beyond_tolerance_are_reported():
    etl_years = {y: dict(v) for y, v in YEARS.items()}
    etl_years[2024]["n"] = 1190
    del etl_years[2023]
    problems = quality.compare(YEARS, etl_years)
    assert "2023: only in ELT" in problems
    assert any(p.startswith("2024 n: ELT 1200 vs ETL 1190") for p in problems)


def test_tiny_difference_within_tolerance_is_accepted():
    big = {2024: {"n": 1_000_000}}
    assert quality.compare(big, {2024: {"n": 999_500}}, tolerance_pct=0.1) == []


def test_as_dict_and_dropped_pct():
    result = {"columns": ["y", "n", "fires"], "rows": [["2024", "10", None]]}
    assert quality.as_dict(result) == {2024: {"n": 10, "fires": 0}}
    assert quality.dropped_pct(1000, 990) == 1.0
    assert quality.dropped_pct(0, 0) == 0.0


def test_elt_sql_is_filled_in_and_partition_column_is_last():
    sql = elt.build_sql("defect_lake", "my-bucket")
    assert "{" not in sql and "s3://my-bucket/curated/elt/complaints/" in sql
    assert "partitioned_by = ARRAY['received_year']" in sql
    final_select = sql.rsplit("SELECT", 1)[1]
    assert final_select.strip().startswith("*, year(received_date) AS received_year")


def test_sql_sent_to_athena_has_no_comments_or_semicolons():
    # Athena treats any ';' (even in a comment) as a second statement and rejects the call.
    for sql in [elt.build_sql("db", "b")] + [q for _, q in analyse.load_queries("db", 2024)]:
        assert "--" not in sql and ";" not in sql
    assert elt.strip_comments("-- note; here\nSELECT 1 -- why\n;") == "SELECT 1"


def test_analysis_queries_load_with_titles():
    queries = analyse.load_queries("defect_lake", 2024)
    assert len(queries) == 5
    for title, sql in queries:
        assert title and "{" not in sql and "defect_lake.complaints_elt" in sql
    assert queries[0][0].endswith("received in 2024")


def test_comparison_summary():
    text = analyse.comparison_summary({"scanned_bytes": 400e6, "wall_ms": 3000},
                                      {"scanned_bytes": 4e6, "wall_ms": 900})
    assert "100x less data" in text and "99.0% cheaper" in text


def test_glue_cost_estimate():
    assert etl.dpus({"WorkerType": "G.1X", "NumberOfWorkers": 2}) == 2
    assert round(etl.job_cost({"WorkerType": "G.1X", "NumberOfWorkers": 2, "ExecutionTime": 180}), 4) == 0.044  # 2 DPU x 3 min
    assert round(etl.job_cost({"WorkerType": "G.1X", "NumberOfWorkers": 2, "ExecutionTime": 20}), 4) == 0.0147  # 1-minute minimum
