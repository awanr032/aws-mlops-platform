"""Train the bearing-fault classifier, evaluate it, and refuse to ship it if it is not good enough.

Usage:  python training/train.py --out model --min-accuracy 0.90
Writes  model/model.joblib and model/metrics.json.
Exits with code 1 (failing the build) if accuracy or any class's recall is below the threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import joblib
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(__file__))
from data import CLASSES, FEATURES, generate  # noqa: E402


def train_and_evaluate(n_per_class: int = 1000, seed: int = 42):
    X, y = generate(n_per_class=n_per_class, seed=seed)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=seed
    )
    model = RandomForestClassifier(
        n_estimators=150, max_depth=12, min_samples_leaf=2, random_state=seed, n_jobs=-1
    )
    model.fit(X_train, y_train)
    predicted = model.predict(X_test)

    report = classification_report(y_test, predicted, labels=CLASSES, output_dict=True, zero_division=0)
    metrics = {
        "accuracy": round(accuracy_score(y_test, predicted), 4),
        "recall_per_class": {c: round(report[c]["recall"], 4) for c in CLASSES},
        "confusion_matrix": {
            "labels": CLASSES,
            "rows_true_cols_predicted": confusion_matrix(y_test, predicted, labels=CLASSES).tolist(),
        },
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "features": FEATURES,
        "algorithm": "RandomForestClassifier",
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return model, metrics


def gate(metrics: dict, min_accuracy: float) -> list[str]:
    """Return the reasons this model must not be deployed (empty list = good to ship)."""
    problems = []
    if metrics["accuracy"] < min_accuracy:
        problems.append(f"accuracy {metrics['accuracy']:.3f} is below {min_accuracy:.3f}")
    # A model can look accurate overall while missing one fault type entirely.
    for label, recall in metrics["recall_per_class"].items():
        if recall < min_accuracy - 0.10:
            problems.append(f"recall for {label} is only {recall:.3f}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="model")
    parser.add_argument("--min-accuracy", type=float, default=0.90)
    parser.add_argument("--rows-per-class", type=int, default=1000)
    args = parser.parse_args(argv)

    model, metrics = train_and_evaluate(n_per_class=args.rows_per_class)
    print(json.dumps(metrics, indent=2))

    problems = gate(metrics, args.min_accuracy)
    if problems:
        print("\nQUALITY GATE FAILED - this model will not be deployed:")
        for p in problems:
            print(f"  - {p}")
        return 1

    os.makedirs(args.out, exist_ok=True)
    joblib.dump(model, os.path.join(args.out, "model.joblib"), compress=3)
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nQuality gate passed (accuracy {metrics['accuracy']:.3f}). Saved to {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
