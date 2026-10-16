# Shared storage for Terraform state of the later projects (01-work-order-api onwards).
# Keeping state in S3 lets both your laptop and GitHub Actions work on the same deployment.
# Locking uses S3's native lock file, so no DynamoDB lock table is needed.

resource "aws_s3_bucket" "tfstate" {
  bucket = "aws-mlops-platform-tfstate-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

output "tfstate_bucket" {
  description = "S3 bucket holding Terraform state for the other projects."
  value       = aws_s3_bucket.tfstate.id
}
