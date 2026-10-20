# The workflow itself. Its steps are drawn in workflow.asl.json (Amazon States Language);
# Terraform fills in the function ARNs and table name.

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.name}-workflow"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

# The workflow may run its three functions and write to its one table.
data "aws_iam_policy_document" "sfn_permissions" {
  statement {
    sid     = "RunSteps"
    actions = ["lambda:InvokeFunction"]
    resources = flatten([
      for f in aws_lambda_function.step : [f.arn, "${f.arn}:*"]
    ])
  }

  statement {
    sid       = "SaveResults"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.results.arn]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${var.name}-workflow"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_permissions.json
}

resource "aws_sfn_state_machine" "extraction" {
  name     = var.name
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD" # keeps a visual history of every run in the console

  definition = templatefile("${path.module}/workflow.asl.json", {
    validate_function_arn = aws_lambda_function.step["validate"].arn
    extract_function_arn  = aws_lambda_function.step["extract"].arn
    check_function_arn    = aws_lambda_function.step["check"].arn
    table_name            = aws_dynamodb_table.results.name
  })

  depends_on = [aws_iam_role_policy.sfn]
}
