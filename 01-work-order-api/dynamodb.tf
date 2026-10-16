# One row per work order. On-demand billing: you pay per request, nothing when idle.

resource "aws_dynamodb_table" "work_orders" {
  name         = "${var.name}-work-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "work_order_id"

  attribute {
    name = "work_order_id"
    type = "S"
  }

  attribute {
    name = "asset_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Lets the API list one asset's work orders, newest first, without scanning the table.
  global_secondary_index {
    name            = "asset_id-created_at-index"
    hash_key        = "asset_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}
