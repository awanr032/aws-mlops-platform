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

# The model only does arithmetic on its input, so it needs nothing but its own logs.
data "aws_iam_policy_document" "lambda_permissions" {
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

resource "aws_lambda_function" "model" {
  function_name = var.name
  role          = aws_iam_role.lambda.arn

  # Container mode: code, libraries and the trained model all come from the image.
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.model.repository_url}:${var.image_tag}"
  architectures = ["arm64"] # the image is built on an ARM runner to match

  memory_size = var.memory_mb
  timeout     = 30

  environment {
    variables = {
      MODEL_VERSION = var.image_tag
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
    aws_ecr_repository_policy.lambda_pull,
  ]
}
