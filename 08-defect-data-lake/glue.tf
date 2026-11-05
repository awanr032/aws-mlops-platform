locals {
  bucket      = aws_s3_bucket.lake.bucket
  bucket_arn  = aws_s3_bucket.lake.arn
  raw_columns = jsondecode(file("${path.module}/schema/raw_columns.json"))["columns"]
}

# ---------------------------------------------------------------------------
# Glue Data Catalog: the "table of contents" Athena uses to understand the files
# ---------------------------------------------------------------------------
resource "aws_glue_catalog_database" "lake" {
  name        = var.database_name
  description = "Vehicle defect complaints (NHTSA). Tables: complaints_raw, complaints_elt, etl_complaints."
}

# The raw table is defined here, by hand, rather than by a crawler: the files have no header
# row, so a crawler would name the columns col0..col50. Every column is text at this stage.
resource "aws_glue_catalog_table" "raw" {
  name          = "complaints_raw"
  database_name = aws_glue_catalog_database.lake.name
  table_type    = "EXTERNAL_TABLE"
  description   = "NHTSA complaints exactly as published (tab-separated text, 51 columns, all strings)."
  parameters    = { EXTERNAL = "TRUE", classification = "csv" }

  storage_descriptor {
    location      = "s3://${local.bucket}/raw/complaints/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
      parameters            = { "field.delim" = "\t", "serialization.format" = "\t" }
    }

    dynamic "columns" {
      for_each = local.raw_columns
      content {
        name = columns.value
        type = "string"
      }
    }
  }
}

# ---------------------------------------------------------------------------
# ETL: Glue Spark job + crawler, sharing one role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.name}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# AWS's standard Glue policy: Data Catalog, CloudWatch logs and metrics.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Plus exactly this project's data: read raw and the script, write only the ETL output.
data "aws_iam_policy_document" "glue_data" {
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "ReadRawAndScript"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/raw/*", "${local.bucket_arn}/scripts/*", "${local.bucket_arn}/curated/etl/*"]
  }
  statement {
    sid       = "WriteEtlOutput"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.bucket_arn}/curated/etl/*"]
  }
}

resource "aws_iam_role_policy" "glue_data" {
  name   = "${var.name}-data"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_data.json
}

resource "aws_s3_object" "etl_script" {
  bucket = local.bucket
  key    = "scripts/complaints_etl.py"
  source = "${path.module}/etl/complaints_etl.py"
  etag   = filemd5("${path.module}/etl/complaints_etl.py")
}

resource "aws_glue_job" "etl" {
  name              = "${var.name}-complaints-etl"
  description       = "ETL: raw complaint text → cleaned, typed Parquet partitioned by received year."
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.0" # Spark 3.5, Python 3.11 (the tests pin the same pyspark)
  worker_type       = "G.1X"
  number_of_workers = var.glue_workers
  timeout           = 20 # minutes; a safety net for cost
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${local.bucket}/${aws_s3_object.etl_script.key}"
    python_version  = "3"
  }

  execution_property {
    max_concurrent_runs = 1
  }

  default_arguments = {
    "--RAW_PATH"                         = "s3://${local.bucket}/raw/complaints/"
    "--OUTPUT_PATH"                      = "s3://${local.bucket}/curated/etl/complaints/"
    "--COLUMNS"                          = join(",", local.raw_columns)
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
  }

  depends_on = [aws_iam_role_policy.glue_data, aws_iam_role_policy_attachment.glue_service]
}

# The crawler looks at the Parquet the job wrote, reads its schema and year folders, and
# creates the table etl_complaints. Crawlers are handy when files describe themselves
# (Parquet does; headerless text does not).
resource "aws_glue_crawler" "etl" {
  name          = "${var.name}-etl-crawler"
  description   = "Registers the ETL job's Parquet output as the table etl_complaints."
  role          = aws_iam_role.glue.arn
  database_name = aws_glue_catalog_database.lake.name
  table_prefix  = "etl_"

  s3_target {
    path       = "s3://${local.bucket}/curated/etl/complaints/"
    exclusions = ["**/_SUCCESS", "**/_temporary/**"]
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version  = 1.0
    Grouping = { TableGroupingPolicy = "CombineCompatibleSchemas" }
  })

  depends_on = [aws_iam_role_policy.glue_data, aws_iam_role_policy_attachment.glue_service]
}
