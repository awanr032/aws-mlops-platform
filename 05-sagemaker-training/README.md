# 05 · SageMaker training, model registry and batch scoring

The bearing-fault classifier from project 04, now trained the way ML teams do it on AWS: on a SageMaker machine that exists only while training, versioned in a model registry with an approval status, and used for nightly-style batch scoring.

```
GitHub Actions ─ train ─►  1. data + code to S3
                           2. SageMaker TRAINING JOB: start machine → train.py → model.tar.gz → stop
                           3. quality gate → MODEL REGISTRY: version N = Approved or Rejected

GitHub Actions ─ batch ─►  4. newest APPROVED version → BATCH TRANSFORM: start machine →
                              score every reading → results file in S3 → stop
```

## What's in here

| Path | Runs where | Purpose |
|---|---|---|
| `training/train.py` | SageMaker training machine | Reads the `train`/`test` channels, trains, writes `model.joblib` + `metrics.json` |
| `training/inference.py` | SageMaker batch-transform machine | `model_fn` / `input_fn` / `predict_fn` / `output_fn`: CSV in, `condition,confidence` out |
| `training/data.py` | GitHub Actions | Synthetic bearing features (same as project 04) |
| `pipeline/train_and_register.py` | GitHub Actions | Uploads data and code, starts the job, applies the gate, registers the version |
| `pipeline/batch_score.py` | GitHub Actions | Picks the newest Approved version, runs batch transform, checks the results |
| `pipeline/gate.py` | GitHub Actions | Accuracy ≥ 0.90 and every class's recall ≥ 0.80 |
| `pipeline/cleanup.py` | GitHub Actions | Empties the registry before `terraform destroy` |
| `*.tf` | Terraform | Bucket, SageMaker execution role, registry group |

**Terraform vs scripts:** Terraform owns what should *exist* (bucket, role, registry group). Training and scoring jobs are things that *happen* once and finish, so scripts start them.

## Design choices

- **Same container for training and prediction** (AWS's `sagemaker-scikit-learn:1.4-2-py312`), and the tests pin the same scikit-learn 1.4.2 on Python 3.12, so the saved model always loads where it's used.
- **The registry decides what is used.** Batch scoring takes the newest *Approved* version, never just the newest file. A rejected model is still recorded (with the reason) but never used; rolling back means approving an older version.
- **Every version traces back to its code:** the registry stores the Git commit, the training job name, and the metrics file.
- **Batch transform keeps IDs out of the model:** `InputFilter "$[1:]"` hides the `asset_id` column from the model and `JoinSource "Input"` joins it back onto each prediction.
- **Cost safety:** jobs stop themselves; training has a 15-minute limit; batch files expire after 30 days; no real-time endpoint (billed per hour even when idle).
- **Least privilege:** the SageMaker role can use only this bucket, its own logs and metrics, and pull AWS's scikit-learn image.

## Run it

Actions → **sagemaker-training** → Run workflow:

1. `apply`: bucket, role, empty registry
2. `train`: about 5 minutes; registers version 1 as Approved
3. `batch`: about 6–8 minutes; scores 200 readings and checks them against the known answers
4. `destroy`: empties the registry, deletes everything

## Test locally

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

`tests/test_pipeline.py` includes a local imitation of batch transform (strip ID → predict → join), so the whole scoring path is checked before AWS is involved.

## Cost

| Item | Approx. cost |
|---|---|
| Training job, `ml.m5.large`, ~2 min billable | Under 1p |
| Batch transform, `ml.m5.large`, ~4 min billable | About 1p |
| S3, registry | Pennies / free |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in. Candidate from the smoke test: the first training job was refused with "Access denied for repository sagemaker-scikit-learn" because the image address used the wrong AWS account for London; AWS hosts its containers in a different account per region (London: 764974769150)._
