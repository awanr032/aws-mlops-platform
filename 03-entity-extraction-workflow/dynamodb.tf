# One row per work order: the extracted entities, or the reasons it needs review or failed.

resource "aws_dynamodb_table" "results" {
  name         = "${var.name}-results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "work_order_id"

  attribute {
    name = "work_order_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}
