# 01 · Work-order API

A serverless REST API for maintenance work orders: report a fault on an asset, look it up, list an asset's history, and move it through `open → in_progress → closed`.

```
client ──x-api-key──► API Gateway (REST, v1) ──► Lambda (Python 3.13, arm64) ──► DynamoDB
                       throttling + daily quota      validation + rules             on-demand table
                                                                                     + asset index
```

## Endpoints

All requests need the header `x-api-key`.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/work-orders` | Create a work order (`asset_id`, `description`, optional `priority`) |
| `GET` | `/work-orders/{id}` | Get one work order |
| `GET` | `/work-orders?asset_id=P-101` | List an asset's work orders, newest first |
| `PATCH` | `/work-orders/{id}` | Update `status`, `priority` or `description` |

Rules: priority is `low`, `medium` (default), `high` or `critical`. Status goes `open → in_progress → closed` (or straight to `closed`); closed work orders cannot be changed. Invalid input returns `400` with a message; unknown IDs return `404`; internal errors return `500` without leaking details.

## Design choices

- **REST API rather than HTTP API:** REST APIs support API keys and usage plans (throttling + quotas).
- **On-demand DynamoDB with a GSI on `asset_id` + `created_at`:** listing an asset's history is a query, not a full-table scan.
- **Least-privilege Lambda role:** only its own log group and four actions on its own table.
- **Repository pattern:** business rules are tested against an in-memory store; no AWS needed for tests.
- **Remote state in S3** (bucket from `00-foundation`) with S3-native locking, shared by laptop and CI.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Deploy and destroy

Through GitHub Actions: **Actions → work-order-api → Run workflow → apply** (or **destroy**). Pushes to `main` run tests and `terraform plan`; pull requests run tests only.

From a laptop: `terraform init`, then `terraform apply` / `terraform destroy`.

## Try it (Git Bash)

```bash
terraform init
URL=$(terraform output -raw api_url)
KEY=$(terraform output -raw api_key)

curl -s -X POST "$URL" -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d '{"asset_id":"P-101","description":"Leaking seal on pump","priority":"high"}'
```

## Cost

| Item | Approx. cost |
|---|---|
| API Gateway | First 1M REST calls/month free for 12 months; otherwise ~$3.50 per million |
| Lambda | 1M requests/month free |
| DynamoDB on-demand | Pennies at this scale |
| CloudWatch Logs (7-day retention) | Pennies |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in._
