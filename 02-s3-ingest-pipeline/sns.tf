# One email per processed file. AWS sends a confirmation email first:
# click "Confirm subscription" in it, or no summaries will arrive.

resource "aws_sns_topic" "summaries" {
  name = "${var.name}-summaries"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.notification_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.summaries.arn
  protocol  = "email"
  endpoint  = var.notification_email
}
