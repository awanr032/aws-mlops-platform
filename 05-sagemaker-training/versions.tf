terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket       = "aws-mlops-platform-tfstate-640168439234"
    key          = "05-sagemaker-training/terraform.tfstate"
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
      Component = "05-sagemaker-training"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
