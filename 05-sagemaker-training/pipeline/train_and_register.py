"""Train the bearing classifier on SageMaker, check it, and register it in the model registry.

  1. Create the training and test data and upload them to S3
  2. Upload our code (train.py + inference.py) to S3
  3. Start a SageMaker training job: AWS starts a machine, runs train.py, saves model.tar.gz, stops
  4. Read the model's metrics from model.tar.gz
  5. Quality gate: register the model as Approved or Rejected (Rejected also fails this run)
"""

from __future__ import annotations

import json
import sys

import boto3

import common
from data import CLASSES, FEATURES, generate
from gate import check

TRAIN_ROWS_PER_CLASS = 1000
TEST_ROWS_PER_CLASS = 250
HYPERPARAMETERS = {"n-estimators": 150, "max-depth": 12, "min-samples-leaf": 2}
MAX_TRAINING_SECONDS = 900  # safety net: SageMaker stops the job (and billing) after 15 minutes


def make_datasets() -> tuple[str, str]:
    """Training and test CSVs, generated with different seeds so the test rows are unseen."""
    def as_csv(n, seed):
        X, y = generate(n_per_class=n, seed=seed)
        rows = [[label, *(round(float(v), 4) for v in features)] for features, label in zip(X, y)]
        return common.to_csv(["condition", *FEATURES], rows)
    return as_csv(TRAIN_ROWS_PER_CLASS, 42), as_csv(TEST_ROWS_PER_CLASS, 7)


def training_request(job, role, image, bucket, source_uri) -> dict:
    hyperparameters = {key: json.dumps(value) for key, value in HYPERPARAMETERS.items()}
    hyperparameters.update({  # "script mode": which file AWS's container should download and run
        "sagemaker_program": json.dumps("train.py"),
        "sagemaker_submit_directory": json.dumps(source_uri),
        "sagemaker_region": json.dumps(common.REGION),
    })

    def channel(name):
        return {"ChannelName": name, "ContentType": "text/csv",
                "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix",
                                                "S3Uri": f"s3://{bucket}/data/{name}/",
                                                "S3DataDistributionType": "FullyReplicated"}}}

    return dict(
        TrainingJobName=job,
        RoleArn=role,
        AlgorithmSpecification={
            "TrainingImage": image,
            "TrainingInputMode": "File",
            # SageMaker reads these from the log and graphs them on the job's page in the console.
            "MetricDefinitions": [
                {"Name": "test:accuracy", "Regex": r"test_accuracy=([0-9\.]+)"},
                {"Name": "test:min_recall", "Regex": r"min_recall=([0-9\.]+)"},
            ],
        },
        HyperParameters=hyperparameters,
        InputDataConfig=[channel("train"), channel("test")],
        OutputDataConfig={"S3OutputPath": f"s3://{bucket}/models/"},
        ResourceConfig={"InstanceType": common.INSTANCE_TYPE, "InstanceCount": 1, "VolumeSizeInGB": 5},
        StoppingCondition={"MaxRuntimeInSeconds": MAX_TRAINING_SECONDS},
        Tags=[{"Key": "Project", "Value": "aws-mlops-platform"},
              {"Key": "GitCommit", "Value": common.version_label()}],
    )


def main() -> int:
    bucket = common.setting("BUCKET")
    role = common.setting("ROLE_ARN")
    group = common.setting("MODEL_GROUP")
    image = common.setting("IMAGE_URI")
    session = boto3.Session(region_name=common.REGION)
    s3, sm = session.client("s3"), session.client("sagemaker")
    common.check_quota(session, "training job")

    job = f"bearing-train-{common.timestamp()}"
    version = common.version_label()
    print(f"\n1. Uploading data to s3://{bucket}/data/")
    train_csv, test_csv = make_datasets()
    s3.put_object(Bucket=bucket, Key="data/train/train.csv", Body=train_csv.encode())
    s3.put_object(Bucket=bucket, Key="data/test/test.csv", Body=test_csv.encode())
    print(f"   train.csv: {TRAIN_ROWS_PER_CLASS * len(CLASSES)} rows, "
          f"test.csv: {TEST_ROWS_PER_CLASS * len(CLASSES)} rows")

    source_key = f"code/{job}/sourcedir.tar.gz"
    source_uri = f"s3://{bucket}/{source_key}"
    print(f"2. Uploading code to {source_uri}")
    s3.put_object(Bucket=bucket, Key=source_key, Body=common.package_source())

    print(f"3. Training job {job} on {common.INSTANCE_TYPE} (image {image.split('/')[-1]})")
    sm.create_training_job(**training_request(job, role, image, bucket, source_uri))
    d = common.wait(lambda: sm.describe_training_job(TrainingJobName=job), "TrainingJobStatus")
    if d["TrainingJobStatus"] != "Completed":
        print(f"::error::Training job {d['TrainingJobStatus']}: {d.get('FailureReason')}")
        print("Logs: CloudWatch > Log groups > /aws/sagemaker/TrainingJobs > " + job)
        return 1
    artifact = d["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"   billable time: {d.get('BillableTimeInSeconds')} s, model: {artifact}")

    print("4. Reading metrics from model.tar.gz")
    bucket_name, key = artifact.removeprefix("s3://").split("/", 1)
    tar_bytes = s3.get_object(Bucket=bucket_name, Key=key)["Body"].read()
    metrics = json.loads(common.read_from_tar(tar_bytes, "metrics.json"))
    print(f"   accuracy {metrics['accuracy']}, recall per class {metrics['recall_per_class']}")
    metrics_key = key.rsplit("/", 1)[0] + "/metrics.json"
    s3.put_object(Bucket=bucket_name, Key=metrics_key, Body=json.dumps(metrics, indent=2).encode(),
                  ContentType="application/json")

    passed, reasons = check(metrics)
    status = "Approved" if passed else "Rejected"
    print(f"5. Quality gate: {'PASSED' if passed else 'FAILED'} ({'; '.join(reasons)})")
    package = sm.create_model_package(
        ModelPackageGroupName=group,
        ModelPackageDescription=f"Commit {version}, job {job}. Gate: {'; '.join(reasons)}"[:1000],
        ModelApprovalStatus=status,
        InferenceSpecification={
            "Containers": [{
                "Image": image,
                "ModelDataUrl": artifact,
                "Environment": {  # how the container finds our prediction code at serving time
                    "SAGEMAKER_PROGRAM": "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": source_uri,
                    "SAGEMAKER_REGION": common.REGION,
                },
            }],
            "SupportedContentTypes": ["text/csv"],
            "SupportedResponseMIMETypes": ["text/csv"],
            "SupportedTransformInstanceTypes": [common.INSTANCE_TYPE],
        },
        ModelMetrics={"ModelQuality": {"Statistics": {
            "ContentType": "application/json", "S3Uri": f"s3://{bucket_name}/{metrics_key}"}}},
        CustomerMetadataProperties={
            "git_commit": version,
            "training_job": job,
            "accuracy": str(metrics["accuracy"]),
            "min_class_recall": str(min(metrics["recall_per_class"].values())),
        },
    )
    arn = package["ModelPackageArn"]
    print(f"   registered {arn.split('/')[-2]} version {arn.split('/')[-1]} as {status}")
    if not passed:
        print("::error::Model rejected by the quality gate; batch scoring keeps using the last approved model.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
