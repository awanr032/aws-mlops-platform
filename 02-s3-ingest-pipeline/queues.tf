# The main queue holds "a file arrived" messages until Lambda handles them.
# A message that fails max_receive_count times moves to the dead-letter queue (DLQ),
# where it waits, untouched, for a human to look at it.

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = 1209600 # 14 days, the maximum
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "incoming" {
  name                    = "${var.name}-incoming"
  sqs_managed_sse_enabled = true

  # While Lambda works on a message it is hidden from other workers. AWS recommends
  # at least six times the function timeout so a slow run is not picked up twice.
  visibility_timeout_seconds = var.lambda_timeout_seconds * 6

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only allow the dead-letter queue to receive from our main queue.
resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.incoming.arn]
  })
}

# Only our bucket, in our account, may post messages to the queue.
data "aws_iam_policy_document" "incoming_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.incoming.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.data.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "incoming" {
  queue_url = aws_sqs_queue.incoming.id
  policy    = data.aws_iam_policy_document.incoming_queue.json
}
