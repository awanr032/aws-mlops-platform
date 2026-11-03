"""Empty the model registry before 'terraform destroy'.

Terraform cannot delete a model package group that still contains model versions, and the
versions are created by the pipeline, not by Terraform. So the destroy step runs this first.
"""

from __future__ import annotations

import os

import boto3
from botocore.exceptions import ClientError

import common


def main() -> int:
    group = os.environ.get("MODEL_GROUP") or "bearing-classifier"
    sm = boto3.Session(region_name=common.REGION).client("sagemaker")

    deleted = 0
    try:
        for page in sm.get_paginator("list_model_packages").paginate(ModelPackageGroupName=group):
            for package in page["ModelPackageSummaryList"]:
                sm.delete_model_package(ModelPackageName=package["ModelPackageArn"])
                deleted += 1
    except ClientError as exc:
        print(f"Registry '{group}': {exc.response['Error']['Message']}")
    print(f"Deleted {deleted} model version(s) from '{group}'")

    # Models left behind if a batch run was cancelled half-way (normally deleted straight away).
    for page in sm.get_paginator("list_models").paginate(NameContains="bearing-batch-"):
        for model in page["Models"]:
            sm.delete_model(ModelName=model["ModelName"])
            print(f"Deleted leftover model {model['ModelName']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
