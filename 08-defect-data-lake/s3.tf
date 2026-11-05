# One bucket, organised in zones:
#   raw/complaints/        text files as published by NHTSA (only converted to UTF-8)
#   raw/_manifests/        what was downloaded, when, from where, how many rows
#   curated/elt/complaints Parquet written by Athena SQL (ELT)
#   curated/etl/complaints Parquet written by the Glue Spark job (ETL)
#   scripts/               the Glue job's Python script
#   athena-results/        Athena's answers (deleted after 7 days)
resource "aws_s3_bucket" "lake" {
  bucket        = "${var.name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # learning project: destroy removes the data too
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }
}
