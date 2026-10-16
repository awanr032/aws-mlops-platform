output "api_url" {
  description = "Base URL for work-order requests."
  value       = "${aws_api_gateway_stage.v1.invoke_url}/work-orders"
}

output "api_key" {
  description = "Send this in the x-api-key header. Show it with: terraform output -raw api_key"
  value       = aws_api_gateway_api_key.client.value
  sensitive   = true
}

output "table_name" {
  value = aws_dynamodb_table.work_orders.name
}
