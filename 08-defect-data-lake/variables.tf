variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "name" {
  description = "Prefix for the bucket, Glue job, crawler and Athena workgroup."
  type        = string
  default     = "defect-lake"
}

variable "database_name" {
  description = "Glue Data Catalog database (Athena: FROM defect_lake.<table>). Underscores only."
  type        = string
  default     = "defect_lake"
}

variable "analysis_year" {
  description = "Year of complaints the analysis questions focus on (must be in the downloaded data)."
  type        = number
  default     = 2024
}

variable "glue_workers" {
  description = "Spark workers for the ETL job (G.1X = 1 DPU each, about $0.44 per DPU-hour)."
  type        = number
  default     = 2
}

variable "max_scan_gb_per_query" {
  description = "Athena cancels any query that would read more than this. A safety net for cost."
  type        = number
  default     = 5
}
