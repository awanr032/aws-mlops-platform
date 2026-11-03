"""Shared helpers for the pipeline scripts (run by GitHub Actions, not by SageMaker)."""

from __future__ import annotations

import csv
import io
import os
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
TRAINING = os.path.join(PROJECT, "training")
sys.path.insert(0, TRAINING)

REGION = os.environ.get("AWS_REGION", "eu-west-2")
INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "ml.m5.large")
SOURCE_FILES = ["train.py", "inference.py"]  # what the SageMaker container needs to run


def setting(name: str) -> str:
    """Values Terraform created (bucket, role, ...). The workflow passes them as env vars."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing environment variable {name}. Run 'apply' first; the workflow "
                 f"reads it from 'terraform output'.")
    return value


def version_label() -> str:
    """Short Git commit, so every model in the registry traces back to its code."""
    return os.environ.get("GITHUB_SHA", "local")[:12]


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def to_csv(header, rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if header:
        writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def package_source() -> bytes:
    """Zip the training and inference scripts as sourcedir.tar.gz (SageMaker 'script mode')."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in SOURCE_FILES:
            tar.add(os.path.join(TRAINING, name), arcname=name)
    return buf.getvalue()


def read_from_tar(tar_bytes: bytes, member: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for info in tar.getmembers():
            if info.name.lstrip("./") == member:
                return tar.extractfile(info).read()
    raise KeyError(f"{member} not found in archive")


def wait(describe, status_key: str, done=("Completed", "Failed", "Stopped"), every: int = 20) -> dict:
    """Poll a SageMaker job, printing each change of status, until it finishes."""
    last = None
    while True:
        d = describe()
        now = (d[status_key], d.get("SecondaryStatus"))
        if now != last:
            last = now
            print(f"  {time.strftime('%H:%M:%S')}  {now[0]:11} {now[1] or ''}", flush=True)
        if d[status_key] in done:
            return d
        time.sleep(every)


def check_quota(session, usage: str) -> None:
    """Warn early if the account limit for this machine type is 0 (common on new accounts)."""
    name = f"{INSTANCE_TYPE} for {usage} usage"
    sq = session.client("service-quotas")
    for lister in ("list_service_quotas", "list_aws_default_service_quotas"):
        try:
            for page in sq.get_paginator(lister).paginate(ServiceCode="sagemaker"):
                for q in page["Quotas"]:
                    if q["QuotaName"] == name:
                        print(f"Account limit '{name}': {q['Value']:g}")
                        if q["Value"] < 1:
                            sys.exit(f"The limit is 0. Request 1 in Service Quotas > Amazon SageMaker > "
                                     f"'{name}' (free; may take a day), then run again.")
                        return
        except Exception as exc:  # the check is a convenience; never block on it
            print(f"(could not read quota '{name}': {exc})")
            return
    print(f"(quota '{name}' not found; continuing)")
