variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for every resource in this project."
  type        = string
  default     = "entity-extraction"
}

variable "model_id" {
  description = "Bedrock model used for extraction. Must be available on demand in the region."
  type        = string
  default     = "mistral.ministral-3-14b-instruct"
}

variable "log_retention_days" {
  type    = number
  default = 7
}
