"""ETL: a Glue Spark job that cleans the raw complaints and writes partitioned Parquet.

  EXTRACT   read the raw tab-separated text files from s3://<bucket>/raw/complaints/
  TRANSFORM give columns proper types and names, turn Y/N into true/false, parse dates,
            mark impossible values as missing, drop rows without an ID or received date
  LOAD      write Parquet, one folder per received year, to s3://<bucket>/curated/etl/complaints/
            (a Glue crawler then registers it as the table etl_complaints)

The same rules are written in SQL in elt/complaints_elt.sql; the quality check compares both.
transform() is plain PySpark, so it is tested locally (tests/test_etl_spark.py) without AWS.
"""

from __future__ import annotations

import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType


def blank_to_null(value):
    trimmed = F.trim(value)
    return F.when(trimmed == "", None).otherwise(trimmed)


def text(col: str):
    """Trimmed text, with empty strings treated as missing."""
    return blank_to_null(F.col(col))


def yes_no(col: str):
    value = F.upper(text(col))
    return F.when(value == "Y", True).when(value == "N", False)


def whole_number(col: str, low: int | None = None, high: int | None = None):
    number = text(col).cast("int")
    if low is None:
        return number
    return F.when(number.between(low, high), number)


def yyyymmdd(col: str):
    return F.to_date(text(col), "yyyyMMdd")


def transform(raw: DataFrame) -> DataFrame:
    received = yyyymmdd("ldate")
    return (
        raw.select(
            text("cmplid").cast("bigint").alias("complaint_id"),
            text("odino").cast("bigint").alias("odi_number"),
            text("mfr_name").alias("manufacturer"),
            F.upper(text("maketxt")).alias("make"),
            F.upper(text("modeltxt")).alias("model"),
            whole_number("yeartxt", 1900, 2100).alias("model_year"),  # 9999 = unknown → missing
            text("compdesc").alias("component"),
            blank_to_null(F.split(text("compdesc"), ":").getItem(0)).alias("component_group"),
            yes_no("crash").alias("crash"),
            yes_no("fire").alias("fire"),
            F.coalesce(whole_number("injured"), F.lit(0)).alias("injured"),
            F.coalesce(whole_number("deaths"), F.lit(0)).alias("deaths"),
            yes_no("medical_attn").alias("medical_attention"),
            yes_no("vehicles_towed_yn").alias("towed"),
            yes_no("police_rpt_yn").alias("police_report"),
            whole_number("miles", 0, 2_000_000).alias("miles"),
            whole_number("veh_speed", 0, 200).alias("vehicle_speed"),
            yyyymmdd("faildate").alias("failure_date"),
            received.alias("received_date"),
            text("state").alias("state"),
            text("cmpl_type").alias("complaint_type"),
            text("prod_type").alias("product_type"),
            text("fuel_type").alias("fuel_type"),
            text("drive_train").alias("drive_train"),
            text("cdescr").alias("description"),
            F.year(received).alias("received_year"),
        )
        .where(F.col("complaint_id").isNotNull() & F.col("received_date").isNotNull())
    )


def read_raw(spark: SparkSession, path: str, columns: list[str]) -> DataFrame:
    schema = StructType([StructField(c, StringType()) for c in columns])
    return (spark.read
            .option("sep", "\t")
            .option("quote", "")        # the narratives contain quote marks; they are not field quotes
            .option("header", "false")
            .option("mode", "PERMISSIVE")  # older rows have 49 fields: the last two become missing
            .schema(schema)
            .csv(path))


def write_curated(df: DataFrame, path: str) -> None:
    (df.write.mode("overwrite")
       .partitionBy("received_year")   # one folder per year: queries for one year skip the rest
       .option("compression", "snappy")
       .parquet(path))


def arguments(names: list[str]) -> dict:
    try:
        from awsglue.utils import getResolvedOptions  # available inside Glue
        return getResolvedOptions(sys.argv, names)
    except ImportError:
        import argparse
        parser = argparse.ArgumentParser()
        for name in names:
            parser.add_argument(f"--{name}", required=True)
        return vars(parser.parse_known_args()[0])


def main() -> None:
    args = arguments(["RAW_PATH", "OUTPUT_PATH", "COLUMNS"])
    spark = (SparkSession.builder.appName("complaints-etl")
             .config("spark.sql.ansi.enabled", "false")  # bad numbers/dates become missing, not errors
             .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false")
             .getOrCreate())
    raw = read_raw(spark, args["RAW_PATH"], args["COLUMNS"].split(","))
    curated = transform(raw).cache()
    rows_in, rows_out = raw.count(), curated.count()
    write_curated(curated, args["OUTPUT_PATH"])
    print(f"ETL done: {rows_in} raw rows → {rows_out} curated rows "
          f"({rows_in - rows_out} dropped: no ID or no received date)")


if __name__ == "__main__":
    main()
