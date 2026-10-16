variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for every resource in this project."
  type        = string
  default     = "work-order-api"
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "throttle_rate_limit" {
  description = "Steady-state requests per second allowed per API key."
  type        = number
  default     = 5
}

variable "throttle_burst_limit" {
  description = "Short bursts of requests allowed per API key."
  type        = number
  default     = 10
}

variable "daily_quota" {
  description = "Maximum requests per day per API key."
  type        = number
  default     = 1000
}
