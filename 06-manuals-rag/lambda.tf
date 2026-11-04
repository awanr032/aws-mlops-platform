# Two functions from the same container image, each with its own role and only the
# permissions it needs.

locals {
  embed_model_arn = "arn:aws:bedrock:${var.region}::foundation-model/${var.embed_model_id}"
  chat_model_arn  = "arn:aws:bedrock:${var.region}::foundation-model/${var.chat_model_id}"
  bucket_arn      = aws_s3_bucket.rag.arn

  functions = {
    # Rebuilds the index: reads manuals, embeds every chunk, writes the index.
    indexer = { command = "indexer.handler", timeout = 300, memory = 1024 }
    # Answers questions. API Gateway gives up after 29 s, so stop just before that.
    query = { command = "query.handler", timeout = 28, memory = 1024 }
  }
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

resource "aws_iam_role" "fn" {
  for_each           = local.functions
  name               = "${var.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "indexer" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fn["indexer"].arn}:*"]
  }
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "ReadManualsAndIndex"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/manuals/*", "${local.bucket_arn}/index/*"]
  }
  statement {
    sid       = "WriteIndex"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.bucket_arn}/index/*"]
  }
  statement {
    sid       = "Embed"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embed_model_arn]
  }
}

data "aws_iam_policy_document" "query" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fn["query"].arn}:*"]
  }
  # Without ListBucket, S3 reports a missing manifest as "access denied" instead of "no such key".
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "ReadIndexOnly"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/index/*"]
  }
  statement {
    sid       = "EmbedAndAnswer"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embed_model_arn, local.chat_model_arn]
  }
}

resource "aws_iam_role_policy" "indexer" {
  name   = "${var.name}-indexer"
  role   = aws_iam_role.fn["indexer"].id
  policy = data.aws_iam_policy_document.indexer.json
}

resource "aws_iam_role_policy" "query" {
  name   = "${var.name}-query"
  role   = aws_iam_role.fn["query"].id
  policy = data.aws_iam_policy_document.query.json
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each          = local.functions
  name              = "/aws/lambda/${var.name}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "fn" {
  for_each = local.functions

  function_name = "${var.name}-${each.key}"
  role          = aws_iam_role.fn[each.key].arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.rag.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  timeout       = each.value.timeout
  memory_size   = each.value.memory

  image_config {
    command = [each.value.command]
  }

  environment {
    variables = {
      BUCKET           = aws_s3_bucket.rag.bucket
      EMBED_MODEL_ID   = var.embed_model_id
      EMBED_DIMENSIONS = tostring(var.embed_dimensions)
      CHAT_MODEL_ID    = var.chat_model_id
      TOP_K            = tostring(var.top_k)
      IMAGE_TAG        = var.image_tag
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.fn,
    aws_iam_role_policy.indexer,
    aws_iam_role_policy.query,
    aws_ecr_repository_policy.lambda_pull,
  ]
}
