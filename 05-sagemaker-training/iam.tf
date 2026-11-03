# The role SageMaker's machines use while training or scoring. Only what they need:
# this project's bucket, their own logs and metrics, and pulling AWS's scikit-learn image.

locals {
  account   = data.aws_caller_identity.current.account_id
  image_uri = "${var.sklearn_image_account}.dkr.ecr.${var.region}.amazonaws.com/sagemaker-scikit-learn:${var.sklearn_image_tag}"
}

data "aws_iam_policy_document" "sagemaker_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
    # Only SageMaker jobs in this account may use the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_iam_role" "sagemaker" {
  name               = "sagemaker-bearing-execution"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_trust.json
}

data "aws_iam_policy_document" "sagemaker" {
  statement {
    sid       = "ProjectBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.ml.arn]
  }
  statement {
    sid       = "ProjectObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.ml.arn}/*"]
  }
  statement {
    sid = "JobLogs"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
    "logs:DescribeLogStreams"]
    resources = ["arn:aws:logs:${var.region}:${local.account}:log-group:/aws/sagemaker/*"]
  }
  statement {
    sid       = "JobMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"] # this action has no resource-level control; the condition limits it
    condition {
      test     = "StringLike"
      variable = "cloudwatch:namespace"
      values   = ["/aws/sagemaker/*"]
    }
  }
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid       = "PullScikitLearnImage"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = ["arn:aws:ecr:${var.region}:${var.sklearn_image_account}:repository/sagemaker-scikit-learn"]
  }
}

resource "aws_iam_role_policy" "sagemaker" {
  name   = "bearing-training-and-scoring"
  role   = aws_iam_role.sagemaker.id
  policy = data.aws_iam_policy_document.sagemaker.json
}
