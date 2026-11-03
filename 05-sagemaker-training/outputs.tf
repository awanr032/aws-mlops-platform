# The workflow passes these to the pipeline scripts as environment variables.
output "bucket" {
  value = aws_s3_bucket.ml.bucket
}

output "role_arn" {
  value = aws_iam_role.sagemaker.arn
}

output "model_group" {
  value = aws_sagemaker_model_package_group.bearing.model_package_group_name
}

output "image_uri" {
  value = local.image_uri
}
