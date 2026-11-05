"""ETL: run the Glue Spark job, then the Glue crawler that registers its output as a table.

  Glue job      reads raw text, transforms with Spark, writes Parquet to curated/etl/complaints/
  Glue crawler  looks at those Parquet files, works out the columns and the year partitions,
                and creates/updates the table etl_complaints in the Glue Data Catalog
"""

from __future__ import annotations

import os
import sys
import time

import athena

DPU_HOUR_USD = 0.44


def wait_for_job(glue, job: str, run_id: str, poll: float = 20, sleep=time.sleep) -> dict:
    last = None
    while True:
        run = glue.get_job_run(JobName=job, RunId=run_id)["JobRun"]
        if run["JobRunState"] != last:
            last = run["JobRunState"]
            print(f"   {time.strftime('%H:%M:%S')}  {last}", flush=True)
        if last in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR", "EXPIRED"):
            return run
        sleep(poll)


def wait_for_crawler(glue, crawler: str, poll: float = 15, sleep=time.sleep) -> dict:
    sleep(poll)  # give the crawler a moment to leave READY
    while True:
        info = glue.get_crawler(Name=crawler)["Crawler"]
        if info["State"] == "READY":
            return info.get("LastCrawl", {})
        print(f"   {time.strftime('%H:%M:%S')}  crawler {info['State']}", flush=True)
        sleep(poll)


DPU_PER_WORKER = {"G.1X": 1, "G.2X": 2, "G.4X": 4, "G.8X": 8}


def dpus(run: dict) -> float:
    if run.get("WorkerType"):
        return run.get("NumberOfWorkers", 0) * DPU_PER_WORKER.get(run["WorkerType"], 1)
    return run.get("MaxCapacity") or 0


def job_cost(run: dict) -> float:
    """Glue bills DPU-hours: capacity x run time (minimum 1 minute)."""
    seconds = max(run.get("ExecutionTime", 0), 60)
    return dpus(run) * seconds / 3600 * DPU_HOUR_USD


def main() -> int:
    import boto3

    job, crawler, database = os.environ["GLUE_JOB"], os.environ["CRAWLER"], os.environ["DATABASE"]
    glue = boto3.client("glue")

    print(f"1. Starting Glue job {job} (Spark: 2 workers start, run the script, stop)")
    run_id = glue.start_job_run(JobName=job)["JobRunId"]
    run = wait_for_job(glue, job, run_id)
    if run["JobRunState"] != "SUCCEEDED":
        print(f"::error::Glue job {run['JobRunState']}: {run.get('ErrorMessage')}")
        print(f"Logs: CloudWatch > Log groups > /aws-glue/jobs/error and /output, run {run_id}")
        return 1
    print(f"   ran {run.get('ExecutionTime')} s on {dpus(run):g} DPUs ≈ ${job_cost(run):.3f}")

    print(f"2. Starting crawler {crawler} (registers the Parquet output as a table)")
    try:
        glue.start_crawler(Name=crawler)
    except glue.exceptions.CrawlerRunningException:
        print("   already running; waiting for it")
    last = wait_for_crawler(glue, crawler)
    if last.get("Status") != "SUCCEEDED":
        print(f"::error::Crawler {last.get('Status')}: {last.get('ErrorMessage')}")
        return 1

    table = glue.get_table(DatabaseName=database, Name="etl_complaints")["Table"]
    columns = [f"{c['Name']}:{c['Type']}" for c in table["StorageDescriptor"]["Columns"]]
    keys = [f"{k['Name']}:{k['Type']}" for k in table.get("PartitionKeys", [])]
    print(f"   table etl_complaints: {len(columns)} columns, partitioned by {keys}")
    print("   column types the crawler inferred: " + ", ".join(columns[:8]) + ", ...")

    print("3. Rows per received year in the ETL table")
    print(athena.table(athena.run(
        f"SELECT CAST(received_year AS integer) AS received_year, count(*) AS complaints "
        f"FROM {database}.etl_complaints GROUP BY 1 ORDER BY 1"), limit=50))
    return 0


if __name__ == "__main__":
    sys.exit(main())
