output "function_name" {
  value = aws_lambda_function.model.function_name
}

output "repository_url" {
  value = aws_ecr_repository.model.repository_url
}

output "image_uri" {
  description = "The exact image (code + model version) Lambda is running."
  value       = aws_lambda_function.model.image_uri
}
