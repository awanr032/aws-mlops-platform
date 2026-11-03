"""Training script. SageMaker runs this inside its scikit-learn container.

SageMaker's folder conventions (it sets these environment variables for us):
  SM_CHANNEL_TRAIN  folder with the training CSV, downloaded from S3 before the script starts
  SM_CHANNEL_TEST   folder with the test CSV
  SM_MODEL_DIR      folder whose contents SageMaker zips into model.tar.gz and uploads to S3

Hyperparameters arrive as command-line arguments (--n-estimators 150 ...).
The quality gate is NOT here: this script reports the metrics, and the pipeline decides
whether the model is approved or rejected in the model registry.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, recall_score

FEATURES = ["rms", "kurtosis", "crest_factor", "peak_freq_hz", "shaft_speed_hz"]
LABEL = "condition"


def read_csv(folder_or_file: str):
    """Read a CSV with a header row: condition + the five features. Returns (X, y)."""
    path = folder_or_file
    if os.path.isdir(path):
        files = sorted(f for f in os.listdir(path) if f.endswith(".csv"))
        if not files:
            raise FileNotFoundError(f"no .csv file in {path}")
        path = os.path.join(path, files[0])
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in [LABEL, *FEATURES] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        rows = list(reader)
    X = np.array([[float(r[c]) for c in FEATURES] for r in rows])
    y = [r[LABEL] for r in rows]
    return X, y


def evaluate(model, X, y) -> dict:
    predicted = model.predict(X)
    labels = [str(c) for c in model.classes_]
    recalls = recall_score(y, predicted, labels=labels, average=None)
    return {
        "accuracy": round(float(accuracy_score(y, predicted)), 4),
        "recall_per_class": {label: round(float(r), 4) for label, r in zip(labels, recalls)},
        "confusion_matrix": {"labels": labels,
                             "rows": confusion_matrix(y, predicted, labels=labels).tolist()},
        "test_rows": len(y),
        "sklearn_version": sklearn.__version__,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--n-estimators", type=int, default=150)
    p.add_argument("--max-depth", type=int, default=12)
    p.add_argument("--min-samples-leaf", type=int, default=2)
    p.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    p.add_argument("--test", default=os.environ.get("SM_CHANNEL_TEST", "/opt/ml/input/data/test"))
    p.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    args, _unknown = p.parse_known_args(argv)  # ignore anything extra SageMaker passes
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    X_train, y_train = read_csv(args.train)
    X_test, y_test = read_csv(args.test)
    print(f"Training on {len(y_train)} rows, testing on {len(y_test)} rows "
          f"(scikit-learn {sklearn.__version__})")

    model = RandomForestClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_samples_leaf,
        random_state=42,
        n_jobs=-1,
    ).fit(X_train, y_train)
    model.n_jobs = 1  # predictions are small batches; skip the thread-pool overhead

    metrics = evaluate(model, X_test, y_test)
    metrics["hyperparameters"] = {"n_estimators": args.n_estimators, "max_depth": args.max_depth,
                                  "min_samples_leaf": args.min_samples_leaf}
    print(json.dumps(metrics, indent=2))
    # SageMaker reads these two numbers from the log with a regex and graphs them in the console.
    print(f"test_accuracy={metrics['accuracy']:.4f} min_recall={min(metrics['recall_per_class'].values()):.4f}")

    os.makedirs(args.model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(args.model_dir, "model.joblib"), compress=3)
    with open(os.path.join(args.model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
