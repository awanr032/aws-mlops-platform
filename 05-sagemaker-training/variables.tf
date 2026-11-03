variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "model_group_name" {
  description = "Name of the model registry group that holds every trained version."
  type        = string
  default     = "bearing-classifier"
}

# AWS publishes its ready-made scikit-learn container from a different AWS account in each region.
# London: 764974769150. The same image trains the model and serves predictions.
variable "sklearn_image_account" {
  type    = string
  default = "764974769150"
}

variable "sklearn_image_tag" {
  description = "scikit-learn 1.4.2 on Python 3.12. Fallback proven in the smoke test: 1.2-1-cpu-py3."
  type        = string
  default     = "1.4-2-py312-cpu-py3"
}

variable "old_files_days" {
  description = "Batch inputs and outputs are deleted after this many days."
  type        = number
  default     = 30
}
