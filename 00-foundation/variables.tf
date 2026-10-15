variable "region" {
  description = "AWS region used for every project in this repo."
  type        = string
  default     = "eu-west-2"
}

variable "budget_email" {
  description = "Email address that receives budget alerts."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD."
  type        = number
  default     = 10
}

variable "github_owner" {
  description = "GitHub user or organisation that owns the repo."
  type        = string
  default     = "awanr032"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the deploy role."
  type        = string
  default     = "aws-mlops-platform"
}

variable "log_retention_days" {
  description = "Days to keep CloudTrail logs in S3 before they are deleted."
  type        = number
  default     = 90
}
