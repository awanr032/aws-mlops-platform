# One bucket for everything SageMaker reads and writes:
#   data/     training and test CSVs          code/   our scripts (sourcedir.tar.gz)
#   models/   model.tar.gz + metrics.json     batch/  input readings, raw output, predictions.csv
resource "aws_s3_bucket" "ml" {
  bucket        = "sagemaker-bearing-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # learning project: destroy removes the files too
}

resource "aws_s3_bucket_public_access_block" "ml" {
  bucket                  = aws_s3_bucket.ml.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ml" {
  bucket = aws_s3_bucket.ml.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "ml" {
  bucket = aws_s3_bucket.ml.id
  rule {
    id     = "expire-batch-files"
    status = "Enabled"
    filter {
      prefix = "batch/"
    }
    expiration {
      days = var.old_files_days
    }
  }
}
