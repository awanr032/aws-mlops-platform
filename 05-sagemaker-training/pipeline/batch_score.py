"""Score a file of bearing readings with the latest APPROVED model, using SageMaker batch transform.

  1. Find the newest Approved model in the registry (never just "the newest model")
  2. Upload a file of readings: asset_id + five features per line
  3. Batch transform: AWS starts a machine, scores every line, writes a results file, stops
     - the asset_id column is hidden from the model (InputFilter) and joined back afterwards (JoinSource)
  4. Check the results against the known answers and save a clean predictions.csv
"""

from __future__ import annotations

import sys
from collections import Counter

import boto3
import numpy as np

import common
from data import generate

ROWS_PER_CLASS = 50  # 200 readings in total
MIN_BATCH_ACCURACY = 0.90


def make_batch(seed: int = 2026) -> tuple[str, dict]:
    """Readings in random order, as a header-less CSV, plus the true condition of each asset."""
    X, y = generate(n_per_class=ROWS_PER_CLASS, seed=seed)
    order = np.random.default_rng(seed).permutation(len(y))
    rows, truth = [], {}
    for n, i in enumerate(order, start=1):
        asset = f"BRG-{n:04d}"
        rows.append([asset, *(round(float(v), 4) for v in X[i])])
        truth[asset] = y[i]
    return common.to_csv(None, rows), truth


def summarise(output_text: str, truth: dict) -> dict:
    """Parse joined output lines (asset_id, 5 features, condition, confidence) and compare to truth."""
    predictions = {}
    for line in output_text.splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 8:
            raise ValueError(f"Unexpected output line ({len(parts)} columns): {line!r}")
        predictions[parts[0]] = (parts[6], float(parts[7]))
    scored = [a for a in truth if a in predictions]
    correct = sum(predictions[a][0] == truth[a] for a in scored)
    return {
        "rows_in": len(truth),
        "rows_out": len(predictions),
        "missing": sorted(set(truth) - set(predictions)),
        "accuracy": round(correct / len(scored), 4) if scored else 0.0,
        "by_condition": dict(Counter(p[0] for p in predictions.values())),
        "mistakes": [(a, truth[a], predictions[a][0], predictions[a][1])
                     for a in scored if predictions[a][0] != truth[a]],
        "predictions": predictions,
    }


def latest_approved(sm, group: str) -> str:
    found = sm.list_model_packages(ModelPackageGroupName=group, ModelApprovalStatus="Approved",
                                   SortBy="CreationTime", SortOrder="Descending", MaxResults=1)
    packages = found["ModelPackageSummaryList"]
    if not packages:
        sys.exit(f"No Approved model in '{group}'. Run 'train' first.")
    return packages[0]["ModelPackageArn"]


def main() -> int:
    bucket = common.setting("BUCKET")
    role = common.setting("ROLE_ARN")
    group = common.setting("MODEL_GROUP")
    session = boto3.Session(region_name=common.REGION)
    s3, sm = session.client("s3"), session.client("sagemaker")
    common.check_quota(session, "transform job")

    package_arn = latest_approved(sm, group)
    details = sm.describe_model_package(ModelPackageName=package_arn)
    meta = details.get("CustomerMetadataProperties", {})
    print(f"1. Using {group} version {package_arn.split('/')[-1]} "
          f"(commit {meta.get('git_commit')}, test accuracy {meta.get('accuracy')})")

    run = common.timestamp()
    input_csv, truth = make_batch()
    input_prefix, output_prefix = f"batch/input/{run}", f"batch/output/{run}"
    s3.put_object(Bucket=bucket, Key=f"{input_prefix}/readings.csv", Body=input_csv.encode())
    print(f"2. Uploaded {len(truth)} readings to s3://{bucket}/{input_prefix}/readings.csv")

    model_name = f"bearing-batch-{run}"
    job = f"bearing-score-{run}"
    sm.create_model(ModelName=model_name, ExecutionRoleArn=role,
                    PrimaryContainer={"ModelPackageName": package_arn})
    try:
        print(f"3. Batch transform job {job} on {common.INSTANCE_TYPE}")
        sm.create_transform_job(
            TransformJobName=job,
            ModelName=model_name,
            BatchStrategy="MultiRecord",  # send many lines per request instead of one at a time
            MaxPayloadInMB=6,
            TransformInput={
                "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix",
                                                "S3Uri": f"s3://{bucket}/{input_prefix}/"}},
                "ContentType": "text/csv",
                "SplitType": "Line",
            },
            TransformOutput={"S3OutputPath": f"s3://{bucket}/{output_prefix}/",
                             "Accept": "text/csv", "AssembleWith": "Line"},
            TransformResources={"InstanceType": common.INSTANCE_TYPE, "InstanceCount": 1},
            DataProcessing={"InputFilter": "$[1:]",   # the model sees columns 2-6 only (no asset_id)
                            "JoinSource": "Input"},    # output = original line + prediction
            Tags=[{"Key": "Project", "Value": "aws-mlops-platform"}],
        )
        d = common.wait(lambda: sm.describe_transform_job(TransformJobName=job), "TransformJobStatus")
    finally:
        sm.delete_model(ModelName=model_name)  # just a pointer to the package; the registry keeps the model

    if d["TransformJobStatus"] != "Completed":
        print(f"::error::Batch transform {d['TransformJobStatus']}: {d.get('FailureReason')}")
        print("Logs: CloudWatch > Log groups > /aws/sagemaker/TransformJobs > " + job)
        return 1

    output = s3.get_object(Bucket=bucket, Key=f"{output_prefix}/readings.csv.out")["Body"].read().decode()
    result = summarise(output, truth)
    results_key = f"batch/results/{run}/predictions.csv"
    s3.put_object(Bucket=bucket, Key=results_key, Body=common.to_csv(
        ["asset_id", "predicted_condition", "confidence"],
        [[a, c, p] for a, (c, p) in sorted(result["predictions"].items())]).encode())

    print(f"4. Results: s3://{bucket}/{results_key}")
    print(f"   rows in {result['rows_in']}, rows out {result['rows_out']}, accuracy {result['accuracy']}")
    print(f"   predicted conditions: {result['by_condition']}")
    for asset, actual, predicted, confidence in result["mistakes"][:10]:
        print(f"   mistake: {asset} is {actual}, predicted {predicted} ({confidence:.2f})")
    print("   first lines of the raw output:")
    for line in output.splitlines()[:3]:
        print("   |", line)

    if result["missing"] or result["accuracy"] < MIN_BATCH_ACCURACY:
        print("::error::Batch output incomplete or less accurate than expected")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
