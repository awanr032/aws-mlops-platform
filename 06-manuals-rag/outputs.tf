output "ask_url" {
  description = "POST {\"question\": \"...\"} here, with the header x-api-key."
  value       = "${aws_api_gateway_stage.v1.invoke_url}/ask"
}

output "api_url" {
  value = aws_api_gateway_stage.v1.invoke_url
}

output "api_key" {
  value     = aws_api_gateway_api_key.client.value
  sensitive = true
}

output "bucket" {
  value = aws_s3_bucket.rag.bucket
}

output "repository_url" {
  value = aws_ecr_repository.rag.repository_url
}

output "function_names" {
  value = { for k, f in aws_lambda_function.fn : k => f.function_name }
}
