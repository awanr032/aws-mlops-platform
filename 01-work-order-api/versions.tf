terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # State lives in the bucket created by 00-foundation, so your laptop and
  # GitHub Actions share one record of what is deployed.
  backend "s3" {
    bucket       = "aws-mlops-platform-tfstate-640168439234"
    key          = "01-work-order-api/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "aws-mlops-platform"
      Component = "01-work-order-api"
      ManagedBy = "terraform"
    }
  }
}
