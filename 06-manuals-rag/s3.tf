# manuals/  the documents (uploaded by the workflow; anyone with access could add more)
# index/    manifest.json + index/<build_id>/faiss.index and chunks.json (written by the indexer)
resource "aws_s3_bucket" "rag" {
  bucket        = "${var.name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # learning project: destroy removes the files too
}

resource "aws_s3_bucket_public_access_block" "rag" {
  bucket                  = aws_s3_bucket.rag.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "rag" {
  bucket = aws_s3_bucket.rag.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Adding, changing or deleting a manual starts the indexer (event-driven, like project 02).
# The prefix filter matters: the indexer writes to index/, which must NOT trigger it again.
resource "aws_s3_bucket_notification" "manual_changed" {
  bucket = aws_s3_bucket.rag.id

  dynamic "lambda_function" {
    for_each = [".md", ".txt"]
    content {
      lambda_function_arn = aws_lambda_function.fn["indexer"].arn
      events              = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
      filter_prefix       = "manuals/"
      filter_suffix       = lambda_function.value
    }
  }

  depends_on = [aws_lambda_permission.s3_invokes_indexer]
}

resource "aws_lambda_permission" "s3_invokes_indexer" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.fn["indexer"].function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.rag.arn
  source_account = data.aws_caller_identity.current.account_id
}
