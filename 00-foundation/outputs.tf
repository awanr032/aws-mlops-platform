output "account_id" {
  value = local.account_id
}

output "logs_bucket" {
  value = aws_s3_bucket.logs.id
}

output "cloudtrail_arn" {
  value = aws_cloudtrail.audit.arn
}

output "github_deploy_role_arn" {
  description = "Save this as the AWS_DEPLOY_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.github_deploy.arn
}
