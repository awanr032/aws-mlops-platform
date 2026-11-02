# 04 · Lambda model container

A bearing-fault classifier packaged as a container image, built and pushed to ECR by GitHub Actions behind an automated accuracy gate, and served from AWS Lambda.

```
git push ─► GitHub Actions (ARM runner)
              1. unit tests
              2. docker build ─ stage 1: train model ─► quality gate (fails the build if not good enough)
                              └ stage 2: code + libraries + approved model
              3. push image to ECR, tagged with the Git commit (immutable, scanned on push)
              4. terraform apply: Lambda now runs that exact image
              5. smoke test: one cold and one warm prediction
```

## The model

Input: five condition-monitoring features from a rolling-element bearing.

| Feature | Meaning |
|---|---|
| `rms` | Overall vibration level |
| `kurtosis` | Impulsiveness of the signal; impacts from surface damage raise it |
| `crest_factor` | Peak relative to RMS |
| `peak_freq_hz` | Dominant frequency in the envelope spectrum |
| `shaft_speed_hz` | Running speed; fault frequencies are multiples of it (BPFO, BPFI, BSF) |

Output: `healthy`, `inner_race_fault`, `outer_race_fault` or `ball_fault`, with confidence and per-class probabilities.

Training data is synthetic, generated from textbook fault signatures (`training/data.py`), with deliberate overlap between classes. A real dataset such as CWRU can replace it without other changes.

## Quality gate

`training/train.py` fails the build unless overall accuracy is at least 0.90 **and** every class's recall is at least 0.80, because a model can look accurate overall while missing one fault type. During development, a first version without `shaft_speed_hz` reached 90.7% accuracy but only 78% recall on outer-race faults; the gate refused it. Adding shaft speed (the physically correct input, since fault frequencies scale with it) raised accuracy to 99.1%.

## Design choices

- **Train inside the image build**, on the same base image that serves the model: identical Python, scikit-learn and NumPy versions at training and inference time, so the saved model always loads.
- **Immutable image tags = Git commit:** any running version can be traced to its exact code, and rolled back by deploying an older tag.
- **ARM end to end:** built on a GitHub ARM runner, run on arm64 Lambda (cheaper per millisecond than x86).
- **Model loaded once per container:** the first request after idle (a cold start) loads it; later requests reuse it. Responses report `cold_start`, `model_load_ms` and `elapsed_ms`.
- **ECR scan on push and lifecycle policy** (keep the newest 5 images).
- **Least privilege:** the function needs only its log group; the ECR policy lets Lambda pull images only for functions in this account.
- **No public endpoint:** called with `aws lambda invoke`, authenticated by IAM.

## Try it

```bash
aws lambda invoke --function-name bearing-classifier \
  --cli-binary-format raw-in-base64-out \
  --payload file://examples/inner_race.json response.json && cat response.json
```

Other examples: `healthy.json`, `outer_race.json`, `ball.json`, `batch.json` (four readings in one call), `invalid.json` (returns a clear error).

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Cost

| Item | Approx. cost |
|---|---|
| ECR storage (image ~250 MB, newest 5 kept) | Pennies per month |
| Lambda (1 GB, arm64) | Within the free allowance at this scale |
| GitHub ARM runner | Free for public repositories |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in. Already one good story: the quality gate rejected the first model (78% outer-race recall) and showed that shaft speed was a missing input._
