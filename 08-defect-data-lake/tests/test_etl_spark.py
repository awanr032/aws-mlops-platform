"""The Glue job's Spark code, run locally on sample rows (needs pyspark and Java)."""

import datetime as dt
import re

import pytest

pyspark = pytest.importorskip("pyspark")

import complaints_etl  # noqa: E402
import elt  # noqa: E402
from conftest import make_line  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = (SparkSession.builder.master("local[1]").appName("test")
               .config("spark.sql.ansi.enabled", "false")
               .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
               .config("spark.ui.enabled", "false").getOrCreate())
    yield session
    session.stop()


@pytest.fixture(scope="module")
def curated(spark, tmp_path_factory, request):
    from conftest import COLUMNS

    lines = [
        make_line(),                                                      # typical row
        make_line(49, cmplid="1834002", yeartxt="9999", crash="Y", fire="Y", injured="2",
                  compdesc="ELECTRICAL SYSTEM", miles="99999999", ldate="20240301"),  # older 49-field row
        make_line(cmplid="", ldate="20240301"),                           # no ID → dropped
        make_line(cmplid="1834004", ldate=""),                            # no received date → dropped
        make_line(cmplid="1834005", faildate="20230231", maketxt="  ", compdesc=":X", injured=""),
    ]
    path = tmp_path_factory.mktemp("raw") / "complaints.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = complaints_etl.read_raw(spark, str(path), COLUMNS)
    return {r["complaint_id"]: r for r in complaints_etl.transform(raw).collect()}


def test_rows_without_id_or_received_date_are_dropped(curated):
    assert sorted(curated) == [1834001, 1834002, 1834005]


def test_typical_row_is_typed_and_cleaned(curated):
    row = curated[1834001]
    assert row["make"] == "FORD" and row["model"] == "FOCUS" and row["model_year"] == 2019
    assert row["component_group"] == "ENGINE AND ENGINE COOLING"
    assert row["crash"] is False and row["towed"] is True
    assert row["failure_date"] == dt.date(2023, 1, 5) and row["received_year"] == 2023
    assert row["miles"] == 64000 and row["vehicle_speed"] == 65
    assert row["description"] == 'ENGINE STALLED ON "HIGHWAY".'  # quotes kept as text


def test_old_49_field_row_and_unknown_values(curated):
    row = curated[1834002]
    assert row["model_year"] is None        # 9999 = unknown
    assert row["miles"] is None             # impossible mileage
    assert row["crash"] is True and row["fire"] is True and row["injured"] == 2
    assert row["received_year"] == 2024


def test_invalid_date_blank_text_and_missing_numbers(curated):
    row = curated[1834005]
    assert row["failure_date"] is None      # 31 February
    assert row["make"] is None              # blank → missing
    assert row["component_group"] is None   # ":X" has an empty first part
    assert row["injured"] == 0              # missing count → 0


def test_spark_and_sql_produce_the_same_columns_in_the_same_order(spark, columns):
    from pyspark.sql.types import StringType, StructField, StructType

    empty = spark.createDataFrame([], StructType([StructField(c, StringType()) for c in columns]))
    spark_columns = complaints_etl.transform(empty).columns
    sql = elt.build_sql("db", "b")
    select = sql.split("WITH cleaned AS (", 1)[1].split("FROM db.complaints_raw", 1)[0]
    sql_columns = re.findall(r"AS (\w+),?\s*$", select, flags=re.M) + ["received_year"]
    assert spark_columns == sql_columns


def test_write_creates_year_partitions(spark, tmp_path, curated, columns):
    rows = [make_line(cmplid=str(n), ldate=f"{y}0101") for n, y in enumerate([2023, 2024, 2024], 1)]
    src = tmp_path / "in.txt"
    src.write_text("\n".join(rows) + "\n")
    out = tmp_path / "out"
    complaints_etl.write_curated(complaints_etl.transform(complaints_etl.read_raw(spark, str(src), columns)), str(out))
    folders = sorted(p.name for p in out.iterdir() if p.is_dir())
    assert folders == ["received_year=2023", "received_year=2024"]
