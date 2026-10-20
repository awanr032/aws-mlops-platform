output "state_machine_arn" {
  value = aws_sfn_state_machine.extraction.arn
}

output "table_name" {
  value = aws_dynamodb_table.results.name
}

output "console_url" {
  description = "Open this to watch runs as a live diagram."
  value       = "https://${var.region}.console.aws.amazon.com/states/home?region=${var.region}#/statemachines/view/${aws_sfn_state_machine.extraction.arn}"
}
