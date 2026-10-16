# REST API: /work-orders and /work-orders/{id}, all requiring an API key.

resource "aws_api_gateway_rest_api" "this" {
  name        = var.name
  description = "Maintenance work-order API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "work_orders" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "work-orders"
}

resource "aws_api_gateway_resource" "work_order" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.work_orders.id
  path_part   = "{id}"
}

locals {
  routes = {
    list   = { resource_id = aws_api_gateway_resource.work_orders.id, method = "GET" }
    create = { resource_id = aws_api_gateway_resource.work_orders.id, method = "POST" }
    get    = { resource_id = aws_api_gateway_resource.work_order.id, method = "GET" }
    update = { resource_id = aws_api_gateway_resource.work_order.id, method = "PATCH" }
  }
}

resource "aws_api_gateway_method" "route" {
  for_each = local.routes

  rest_api_id      = aws_api_gateway_rest_api.this.id
  resource_id      = each.value.resource_id
  http_method      = each.value.method
  authorization    = "NONE"
  api_key_required = true
}

# Every route goes straight to the Lambda function ("proxy" integration).
resource "aws_api_gateway_integration" "route" {
  for_each = local.routes

  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.route[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}

# A deployment is a snapshot of the API; redeploy whenever routes change.
resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.work_orders.id,
      aws_api_gateway_resource.work_order.id,
      [for m in aws_api_gateway_method.route : m.id],
      [for i in aws_api_gateway_integration.route : i.id],
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.route]
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = "v1"
}

# API key + usage plan: who may call the API, how fast, and how often.
resource "aws_api_gateway_api_key" "client" {
  name = "${var.name}-client"
}

resource "aws_api_gateway_usage_plan" "this" {
  name = "${var.name}-plan"

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.v1.stage_name
  }

  throttle_settings {
    rate_limit  = var.throttle_rate_limit
    burst_limit = var.throttle_burst_limit
  }

  quota_settings {
    limit  = var.daily_quota
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "client" {
  key_id        = aws_api_gateway_api_key.client.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.this.id
}
