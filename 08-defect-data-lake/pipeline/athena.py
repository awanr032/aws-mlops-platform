"""Run a SQL statement in Athena and wait for the answer.

Every result includes 'scanned_bytes': the amount of S3 data Athena read, which is what
Athena charges for (about $5 per terabyte).
"""

from __future__ import annotations

import os
import time

PRICE_PER_TB = 5.0


class QueryFailed(Exception):
    pass


def client():
    import boto3

    return boto3.client("athena", region_name=os.environ.get("AWS_REGION", "eu-west-2"))


def run(sql: str, athena=None, workgroup: str | None = None, max_rows: int = 1000,
        poll: float = 1.0, sleep=time.sleep) -> dict:
    athena = athena or client()
    workgroup = workgroup or os.environ["WORKGROUP"]
    started = time.perf_counter()
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=workgroup)["QueryExecutionId"]
    while True:
        execution = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        sleep(poll)
    stats = execution.get("Statistics", {})
    if state != "SUCCEEDED":
        reason = execution["Status"].get("StateChangeReason", "no reason given")
        raise QueryFailed(f"{state}: {reason}\n--- SQL ---\n{sql[:2000]}")

    columns, rows = [], []
    if execution.get("StatementType") == "DML":  # SELECT-type queries return rows
        paginator = athena.get_paginator("get_query_results")
        for page in paginator.paginate(QueryExecutionId=qid):
            if not columns:
                columns = [c["Name"] for c in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
            for row in page["ResultSet"]["Rows"]:
                rows.append([d.get("VarCharValue") for d in row["Data"]])
            if len(rows) > max_rows:
                break
        if rows and rows[0] == columns:  # the first row of a SELECT result repeats the header
            rows = rows[1:]
    scanned = stats.get("DataScannedInBytes", 0)
    return {"id": qid, "columns": columns, "rows": rows[:max_rows], "scanned_bytes": scanned,
            "engine_ms": stats.get("EngineExecutionTimeInMillis"),
            "wall_ms": round((time.perf_counter() - started) * 1000),
            "cost_usd": scanned / 1e12 * PRICE_PER_TB}


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n} B"


def table(result: dict, limit: int = 15) -> str:
    """Format result rows as an aligned text table."""
    columns, rows = result["columns"], result["rows"][:limit]
    if not columns:
        return "(no rows)"
    cells = [[("" if v is None else str(v))[:40] for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    line = lambda values: "  ".join(v.ljust(w) for v, w in zip(values, widths))
    out = [line(columns), line(["-" * w for w in widths])] + [line(r) for r in cells]
    return "\n".join(out)
