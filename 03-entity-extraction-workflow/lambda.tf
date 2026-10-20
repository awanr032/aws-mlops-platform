# Three small functions from one code package. Each has one job in the workflow.

locals {
  functions = {
    validate = { handler = "handlers.validate_input", timeout = 10 }
    extract  = { handler = "handlers.extract", timeout = 60 }
    check    = { handler = "handlers.check_output", timeout = 10 }
  }
  model_arn = "arn:aws:bedrock:${var.region}::foundation-model/${var.model_id}"
}

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

# Least privilege: write logs, and call exactly one Bedrock model, nothing else.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [for g in aws_cloudwatch_log_group.lambda : "${g.arn}:*"]
  }

  statement {
    sid       = "CallOneModel"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.model_arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.functions
  name              = "/aws/lambda/${var.name}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "step" {
  for_each = local.functions

  function_name    = "${var.name}-${each.key}"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = each.value.handler
  architectures    = ["arm64"]
  memory_size      = 256
  timeout          = each.value.timeout
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      MODEL_ID = var.model_id
    }
  }

  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
}
