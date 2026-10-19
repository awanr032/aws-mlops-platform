variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for every resource in this project."
  type        = string
  default     = "ingest-pipeline"
}

variable "notification_email" {
  description = "Where file summaries are emailed. Leave empty to skip email."
  type        = string
  default     = ""
}

variable "max_receive_count" {
  description = "How many times a failing message is retried before it moves to the dead-letter queue."
  type        = number
  default     = 3
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 60
}

variable "log_retention_days" {
  type    = number
  default = 7
}
