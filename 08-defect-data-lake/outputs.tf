# The workflow passes these to the pipeline scripts.
output "bucket" {
  value = aws_s3_bucket.lake.bucket
}

output "database" {
  value = aws_glue_catalog_database.lake.name
}

output "workgroup" {
  value = aws_athena_workgroup.lake.name
}

output "glue_job" {
  value = aws_glue_job.etl.name
}

output "crawler" {
  value = aws_glue_crawler.etl.name
}

output "analysis_year" {
  value = var.analysis_year
}
