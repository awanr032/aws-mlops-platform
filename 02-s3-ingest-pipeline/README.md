# 02 · S3 ingest pipeline

An event-driven quality gate for maintenance work-order files. Drop a CSV into `incoming/` and, with no button pressed, every row is checked, clean rows go to `processed/`, bad rows go to `rejected/` with the reason, and a summary is emailed.

```
upload CSV ─► S3 incoming/ ─► SQS queue ─► Lambda (Python) ─┬─► S3 processed/   clean rows
                                  │                         ├─► S3 rejected/    bad rows + reasons
                                  │                         └─► SNS email       "2 accepted, 3 rejected"
                                  └─ fails 3 times ─► dead-letter queue (kept 14 days for inspection)
```

## Rules applied to each row

| Column | Rule |
|---|---|
| `asset_id` | Required, at most 64 characters |
| `date` | Required, `YYYY-MM-DD`, a real date, not in the future |
| `priority` | `low`, `medium`, `high` or `critical` (any capitalisation) |
| `description` | Required, at most 1,000 characters |
| `downtime_hours` | Optional; a number from 0 to 8,760 |
| `technician` | Optional; passed through |

A whole file is refused (with a note in `rejected/<name>.error.txt`) if it is empty, has no data rows, lacks a required column, is over 5 MB or has more than 50,000 rows.

## Reliability design

- **Queue between S3 and Lambda:** bursts of uploads wait their turn; nothing is dropped if Lambda is busy or failing.
- **Retries, then a dead-letter queue:** a message that fails 3 times moves to the DLQ instead of retrying forever or disappearing.
- **Partial batch failures:** Lambda takes up to 5 messages at once and reports only the failed ones, so one bad file does not cause good files to be re-processed.
- **Idempotency:** SQS can deliver a message more than once. A marker object per file version (`_state/<hash>.done`), written with an S3 conditional write (`If-None-Match: *`), makes sure each version is processed and emailed once.
- **Visibility timeout = 6 × Lambda timeout:** a slow run is never picked up by a second worker.
- **Least privilege:** Lambda can read only `incoming/` and `_state/`, write only the output folders, and use only its own queue, topic and logs.

## Try it

After deploying (Actions → ingest-pipeline → Run workflow → apply), confirm the SNS subscription email, then:

```bash
terraform init
BUCKET=$(terraform output -raw bucket)

aws s3 cp sample-data/pump_workorders_oct.csv  s3://$BUCKET/incoming/   # 2 accepted, 3 rejected
aws s3 cp sample-data/wrong_columns.csv        s3://$BUCKET/incoming/   # whole file rejected
aws s3 cp sample-data/not_utf8.csv             s3://$BUCKET/incoming/   # crashes 3x, lands in the DLQ

aws s3 ls s3://$BUCKET --recursive
aws s3 cp s3://$BUCKET/rejected/pump_workorders_oct.csv -
```

The `not_utf8.csv` file is deliberately not UTF-8 text. The code does not handle that case, so it stands in for an unexpected bug: watch the message retry, then appear in the dead-letter queue (SQS console → `ingest-pipeline-dlq` → Send and receive messages → Poll).

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Cost

| Item | Approx. cost |
|---|---|
| S3, SQS, SNS email, Lambda | Within free allowances at this scale |
| CloudWatch Logs (7-day retention) | Pennies |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in._
