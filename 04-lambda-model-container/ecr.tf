# ECR: the private store for this project's container images.

resource "aws_ecr_repository" "model" {
  name = var.name

  # A tag (the Git commit) always points to the same image; nobody can overwrite it.
  image_tag_mutability = "IMMUTABLE"

  # ECR checks every pushed image for known security vulnerabilities.
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  # Let `terraform destroy` remove the repository even when it still holds images.
  force_delete = true
}

# Keep only the newest few images so storage never piles up.
resource "aws_ecr_lifecycle_policy" "model" {
  repository = aws_ecr_repository.model.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the newest ${var.images_to_keep} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.images_to_keep
      }
      action = { type = "expire" }
    }]
  })
}

# Allow the Lambda service, for functions in this account only, to pull images.
data "aws_iam_policy_document" "lambda_pull" {
  statement {
    sid     = "LambdaPull"
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "aws:sourceArn"
      values   = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:*"]
    }
  }
}

resource "aws_ecr_repository_policy" "lambda_pull" {
  repository = aws_ecr_repository.model.name
  policy     = data.aws_iam_policy_document.lambda_pull.json
}
