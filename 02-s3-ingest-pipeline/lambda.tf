data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["__pycache__", "__pycache__/*"]
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Least privilege: read only from incoming/, write only to the output folders,
# use only its own queue, topic and log group.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "ReadUploads"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/incoming/*", "${aws_s3_bucket.data.arn}/_state/*"]
  }

  statement {
    sid     = "WriteResults"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data.arn}/processed/*",
      "${aws_s3_bucket.data.arn}/rejected/*",
      "${aws_s3_bucket.data.arn}/_state/*",
    ]
  }

  # Without ListBucket, S3 answers "access denied" instead of "not found" for a
  # missing marker, and the idempotency check cannot tell the two apart.
  statement {
    sid       = "CheckMarkers"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }

  statement {
    sid       = "ConsumeQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.incoming.arn]
  }

  statement {
    sid       = "SendSummaries"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.summaries.arn]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "validator" {
  function_name    = var.name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = "app.handler"
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = var.lambda_timeout_seconds
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      TOPIC_ARN = aws_sns_topic.summaries.arn
    }
  }

  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
}

# Lambda polls the queue and receives up to 5 messages at a time. With
# ReportBatchItemFailures, only the messages that failed go back to the queue.
resource "aws_lambda_event_source_mapping" "incoming" {
  event_source_arn                   = aws_sqs_queue.incoming.arn
  function_name                      = aws_lambda_function.validator.arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]
}
