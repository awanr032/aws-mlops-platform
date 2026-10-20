# 03 · Entity extraction workflow

A Step Functions workflow that turns free-text maintenance work orders into structured fields with a Bedrock model, checks the model's answer, and stores the result or routes it to human review.

> *"P-101 leaking at mech seal, replaced gasket, 3hrs downtime"*
> → `{"asset": "P-101", "component": "mechanical seal", "fault": "leak", "action": "replaced gasket", "downtime_hours": 3}`

```
ValidateInput ──(InvalidInput)──────────────────────────────► InputRejected (fail)
     │
ExtractEntities  (Bedrock; retries 2s → 4s → 8s if the model is busy)
     │  └─(still failing / permanent error)─► RecordFailure ──► ExtractionFailed (fail)
CheckAnswer      (parse JSON, check types, grounding, emptiness)
     │
IsAnswerUsable? ──yes──► SaveResult    (status: extracted)    ──► Extracted
                └─no───► SaveForReview (status: needs_review) ──► NeedsReview
```

## Design choices

- **Orchestration in Step Functions, not one big Lambda:** each step is small, testable and visible; retries and error branches are part of the workflow definition (`workflow.asl.json`) and appear in the console's run diagram.
- **The model is untrusted input.** `CheckAnswer` parses the reply even when the model wraps it in prose or code fences, checks every field's type and range, flags an asset ID that does not appear in the source text (a simple hallucination guard), and rejects answers with no maintenance content.
- **Human review instead of silent failure:** unusable answers are stored as `needs_review` with the raw model output and the reasons.
- **Retries only where they help:** throttling and temporary Bedrock errors (`ModelBusy`) are retried with exponential backoff and jitter; permission or model-ID errors (`ModelCallFailed`) fail immediately and are recorded.
- **Deterministic prompting:** temperature 0, a fixed JSON schema in the system prompt, one worked example.
- **Direct service integration:** results are written to DynamoDB by Step Functions itself, without a Lambda.
- **Least privilege:** the functions may call exactly one Bedrock model; the workflow may invoke only its three functions and write only to its table.
- **Cost visibility:** token usage per call is logged and stored with each result.

## Model

`mistral.ministral-3-14b-instruct`, called on demand in `eu-west-2` via the Bedrock Converse API. Change `model_id` in `variables.tf` to try another model; nothing else needs to change. Third-party models are subscribed on first use, so call the model once from the CLI as an admin before the first deploy.

## Try it

```bash
terraform init
bash run_examples.sh
```

| Example | Expected outcome |
|---|---|
| `01_pump_seal_leak` | extracted |
| `02_compressor_bearing` | extracted |
| `03_conveyor_belt` | extracted |
| `04_vague_note` | needs_review (no equipment identified) |
| `05_not_maintenance` | needs_review (no maintenance information) |

Outcomes 01–05 depend on the model's answers, so an occasional surprise is possible; that is exactly what the check step and the review path are for.
| `06_empty_text` | InputRejected; the model is never called |

Open the `console_url` output to see each run as a live diagram.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Cost

| Item | Approx. cost |
|---|---|
| Bedrock (small model, ~250 tokens per call) | A fraction of a penny per work order |
| Step Functions (Standard) | 4,000 state transitions/month free; about 8 per run |
| Lambda, DynamoDB | Within free allowances |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in. For example: the first model ID tried was not available on demand in London (`ValidationException: The provided model identifier is invalid`); `aws bedrock list-foundation-models --by-inference-type ON_DEMAND` showed which models were._
