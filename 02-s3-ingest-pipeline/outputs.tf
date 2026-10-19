output "bucket" {
  description = "Upload CSV files to s3://<bucket>/incoming/"
  value       = aws_s3_bucket.data.id
}

output "queue_url" {
  value = aws_sqs_queue.incoming.id
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dead_letter.id
}

output "topic_arn" {
  value = aws_sns_topic.summaries.arn
}
