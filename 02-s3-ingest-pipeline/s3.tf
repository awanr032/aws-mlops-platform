# One bucket, three folders:
#   incoming/   you upload CSV files here
#   processed/  clean rows, ready to use
#   rejected/   bad rows with the reason, or a note explaining why a whole file was refused
#   _state/     small markers that stop the same file being processed twice

resource "aws_s3_bucket" "data" {
  bucket = "${var.name}-${data.aws_caller_identity.current.account_id}"

  # Lets `terraform destroy` remove the bucket even when it still holds files.
  # Fine for a learning project; never do this for data you need to keep.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Tell S3 to announce every new CSV in incoming/ by sending a message to the queue.
resource "aws_s3_bucket_notification" "incoming" {
  bucket = aws_s3_bucket.data.id

  queue {
    queue_arn     = aws_sqs_queue.incoming.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "incoming/"
    filter_suffix = ".csv"
  }

  depends_on = [aws_sqs_queue_policy.incoming]
}
