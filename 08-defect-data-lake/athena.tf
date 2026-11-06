# A dedicated Athena workgroup: its own results folder and a hard limit on data read per query,
# so one careless query can't run up a bill.
resource "aws_athena_workgroup" "lake" {
  name          = var.name
  description   = "Queries over the vehicle defect data lake."
  force_destroy = true

  configuration {
    # Not enforced: the ELT step's CREATE TABLE AS SELECT must write its Parquet to
    # curated/elt/ (external_location), and an enforced workgroup forbids choosing a location.
    # The per-query scan limit below still applies to every query.
    enforce_workgroup_configuration    = false
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.max_scan_gb_per_query * 1024 * 1024 * 1024

    result_configuration {
      output_location = "s3://${local.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# The analysis questions, saved in Athena: Query editor → Saved queries (workgroup defect-lake).
resource "aws_athena_named_query" "analysis" {
  for_each = fileset("${path.module}/analysis", "*.sql")

  name        = trimsuffix(each.value, ".sql")
  description = trimprefix(split("\n", file("${path.module}/analysis/${each.value}"))[0], "-- ")
  workgroup   = aws_athena_workgroup.lake.id
  database    = aws_glue_catalog_database.lake.name
  query = replace(replace(file("${path.module}/analysis/${each.value}"),
  "{database}", var.database_name), "{year}", tostring(var.analysis_year))
}
