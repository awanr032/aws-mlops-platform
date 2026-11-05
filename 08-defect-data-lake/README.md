# 08 · Vehicle defect data lake (S3, Glue, Athena; ETL and ELT)

Real US vehicle safety complaints from NHTSA, hundreds of thousands of rows, turned into a queryable data lake. The same cleaning is done **two ways**, ELT with SQL in Athena and ETL with Spark in Glue, and a quality check proves both give identical results.

```
                         ┌──────────────────── Glue Data Catalog (database defect_lake) ───────────────────┐
                         │  complaints_raw (Terraform)    complaints_elt (Athena CTAS)    etl_complaints (crawler) │
                         └──────────▲─────────────────────────────▲──────────────────────────────▲──────────┘
NHTSA zip ──INGEST──► s3://…/raw/complaints/*.txt ──ELT: Athena SQL──► curated/elt/ (Parquet, by year)
 (extract+load)        text, 51 columns, as published  └─ETL: Glue Spark job─► curated/etl/ (Parquet, by year) ─► crawler
                                                                       │
                                     quality checks (ELT = ETL?) + analysis questions in Athena
```

## Key ideas

| Idea | In this project |
|---|---|
| **Data lake** | Files in S3, organised into zones, described in a catalog, queried with SQL |
| **Raw vs curated zones** | `raw/` keeps the source as published (reprocess any time); `curated/` is cleaned and typed |
| **Glue Data Catalog** | Table definitions only (columns, types, file location, format); the data stays in S3 |
| **Schema-on-read** | Athena applies the table definition when it reads; new files are queryable at once |
| **ELT** (extract, load, transform) | Load raw first, then transform *inside* the lake with SQL: `CREATE TABLE AS SELECT` in Athena |
| **ETL** (extract, transform, load) | Transform with a processing engine (Spark in Glue) on the way to the curated zone |
| **Parquet** | Columnar and compressed: a query reads only the columns it needs |
| **Partitioning** | One folder per received year: `WHERE received_year = 2024` skips the other years |
| **Crawler** | Infers a table from files that describe themselves (Parquet); not used for raw, which has no header |

### ELT or ETL: when to use which

| | ELT (Athena SQL) | ETL (Glue Spark) |
|---|---|---|
| Skills | SQL | Python/Spark |
| Infrastructure | None: serverless, pay per data read | A Spark cluster per run (2 workers here), pay per DPU-hour |
| Good for | Typical cleaning, joins and aggregation; analysts can own it | Complex logic, custom code, ML features, very large or messy inputs, many output formats |
| Here | ~1 minute | ~3–5 minutes including Spark start-up |

## The data

NHTSA Office of Defects Investigation complaints flat file (US public domain): tab-separated, no header, 51 fields ([field list](https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt)). The two newest fields were added in April 2026, so older rows have 49 fields. Both the SQL and Spark versions handle that (missing fields become null). The ingest step tries the published 5-year files (`COMPLAINTS_RECEIVED_2020-2024.zip`, and the current chunk) and records what it found in `raw/_manifests/`.

## Cleaning rules (identical in `elt/complaints_elt.sql` and `etl/complaints_etl.py`)

- Proper types: IDs → bigint, counts → int, `YYYYMMDD` → date, `Y`/`N` → true/false
- Blank text → missing; make and model upper-cased
- Model year `9999` (unknown) → missing; mileage over 2,000,000 or speed over 200 → missing
- `component_group` = text before the first `:` in the component (`ENGINE AND ENGINE COOLING:ENGINE` → `ENGINE AND ENGINE COOLING`)
- Rows without a complaint ID or received date are dropped (and counted)
- Partitioned by `received_year`

## Quality checks (`pipeline/quality.py`)

Completeness (share of rows dropped, max 2%), validity (missing values per key column), uniqueness (duplicate IDs), and **consistency**: per year, the ELT and ETL tables must agree on rows, injuries, deaths, fires and number of makes.

## Run it

Actions → **defect-data-lake** → Run workflow → **all**, or stage by stage: `apply` → `ingest` → `elt` → `etl` → `analyse`. Then **destroy**.

Explore in the console:
- **S3** → `defect-lake-<account>`: the zones, and the `received_year=…` folders
- **Glue** → Data Catalog → Databases → `defect_lake`: three tables, their columns and partitions; **ETL jobs** → run details, logs, metrics; **Crawlers** → what it created
- **Athena** → workgroup `defect-lake` → **Saved queries**; try your own SQL and watch *Data scanned*

## Results from my run

| | |
|---|---|
| Rows ingested | _fill in_ |
| ELT: time, data read | _fill in_ |
| ETL: time, cost | _fill in_ |
| ELT = ETL? | _fill in_ |
| Same question, raw text vs Parquet: data read | _fill in_ (e.g. "400 MB vs 3 MB, 130× less") |

## Test locally

```bash
pip install -r requirements-dev.txt   # includes pyspark 3.5.4 (= Glue 5.0); needs Java
python -m pytest -v
```

The Spark tests run the real Glue job code on sample rows in NHTSA's format (49- and 51-field rows, invalid dates, blanks, unknown years) and check that the Spark and SQL versions produce the same columns in the same order.

## Cost

| Item | Approx. cost |
|---|---|
| S3: ~1 GB raw + curated | Pennies per month |
| Athena: $5 per TB read | Under 1p for the whole pipeline (Parquet queries read megabytes) |
| Glue job: 2 DPU × a few minutes × $0.44/DPU-hour | About 5p per run |
| Glue crawler: billed per DPU-hour, 10-minute minimum | About 4p per run |
| Glue Data Catalog | Free at this size |

A workgroup limit cancels any query that would read more than 5 GB.

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in. One from development: a quality-check bug where Python evaluated `out[key] = value` right side first, so a year column leaked into the comparison; caught by a unit test._
