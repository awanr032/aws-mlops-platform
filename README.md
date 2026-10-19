# aws-mlops-platform

Production-style ML systems on AWS: serverless APIs, event-driven pipelines, SageMaker, Bedrock and RAG, all deployed with Terraform. The projects use maintenance and reliability data throughout.

## Projects

| Folder | What it is | Main services |
|---|---|---|
| [`00-foundation`](00-foundation) | Secure account baseline: audit logging, budget alerts, GitHub OIDC | IAM, CloudTrail, S3, Budgets |
| [`01-work-order-api`](01-work-order-api) | Serverless API for maintenance work orders | API Gateway, Lambda, DynamoDB |
| [`02-s3-ingest-pipeline`](02-s3-ingest-pipeline) | CSV upload → validation → dead-letter queue → email summary | S3 events, SQS, SNS |
| `03-entity-extraction-workflow` | Orchestrated LLM entity extraction with retries and error handling | Step Functions, Bedrock |
| `04-lambda-model-container` | Containerised ML model built and pushed by CI | ECR, Lambda, GitHub Actions |
| `05-sagemaker-training` | Training job, model registry, batch transform, serverless endpoint | SageMaker |
| `06-manuals-rag` | Question answering over maintenance manuals with cited sources | Bedrock embeddings, FAISS on S3 |
| `07-observability` | Logging, tracing, dashboards and alarms for earlier projects | CloudWatch, X-Ray |
| `08-defect-data-lake` | Vehicle defect complaints as a queryable data lake | S3, Glue, Athena |
| `09-distilled-model-serving` | Serving a fine-tuned small model, with accuracy, latency and cost measured | API Gateway, Lambda, Bedrock |

## Conventions

- **Infrastructure as code:** every project is Terraform; `terraform apply` builds it, `terraform destroy` removes it.
- **No long-lived keys:** GitHub Actions authenticates to AWS through OIDC.
- **Cost-aware:** every project README records what it actually cost and how it was torn down.
- **Honest write-ups:** each README includes one thing that went wrong and how it was fixed.

Region: `eu-west-2` (London).
