variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Name of the image repository and the Lambda function."
  type        = string
  default     = "bearing-classifier"
}

variable "image_tag" {
  description = "Which image version Lambda runs. The workflow sets this to the Git commit."
  type        = string
  default     = "bootstrap"
}

variable "memory_mb" {
  description = "Lambda memory. More memory also means more CPU, so faster model loading."
  type        = number
  default     = 1024
}

variable "images_to_keep" {
  description = "Older images beyond this number are deleted automatically."
  type        = number
  default     = 5
}

variable "log_retention_days" {
  type    = number
  default = 7
}
