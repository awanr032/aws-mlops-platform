variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for the image repository, functions and API."
  type        = string
  default     = "manuals-rag"
}

variable "image_tag" {
  description = "Which image version both functions run. The workflow sets this to the Git commit."
  type        = string
  default     = "bootstrap"
}

variable "embed_model_id" {
  description = "Bedrock model that turns text into vectors (embeddings)."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embed_dimensions" {
  description = "Length of each embedding vector. Titan V2 supports 256, 512 or 1024."
  type        = number
  default     = 1024
}

variable "chat_model_id" {
  description = "Bedrock model that writes the answer (the one proven in project 03)."
  type        = string
  default     = "mistral.ministral-3-14b-instruct"
}

variable "top_k" {
  description = "How many chunks are retrieved and given to the model for each question."
  type        = number
  default     = 4
}

# Every question costs a little Bedrock money, so the API is rate-limited and capped per day.
variable "throttle_rate_limit" {
  type    = number
  default = 2
}

variable "throttle_burst_limit" {
  type    = number
  default = 5
}

variable "daily_quota" {
  type    = number
  default = 300
}

variable "images_to_keep" {
  type    = number
  default = 5
}

variable "log_retention_days" {
  type    = number
  default = 7
}
