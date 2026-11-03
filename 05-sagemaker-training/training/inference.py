"""Prediction functions. SageMaker's scikit-learn container calls these during batch transform.

The container's web server calls them in this order for every request:
  model_fn(model_dir)            once per machine: load the model from the unpacked model.tar.gz
  input_fn(body, content_type)   turn the request body (CSV lines) into a feature array
  predict_fn(data, model)        run the model
  output_fn(prediction, accept)  turn predictions into the response body (CSV lines)

Input lines: rms,kurtosis,crest_factor,peak_freq_hz,shaft_speed_hz   (no header, no ID column;
batch transform strips the asset ID before calling us and joins it back afterwards).
Output lines: condition,confidence
"""

from __future__ import annotations

import os

import joblib
import numpy as np

N_FEATURES = 5


def model_fn(model_dir):
    model = joblib.load(os.path.join(model_dir, "model.joblib"))
    model.n_jobs = 1
    return model


def input_fn(body, content_type="text/csv"):
    if content_type.split(";")[0].strip() != "text/csv":
        raise ValueError(f"Unsupported content type {content_type!r}; send text/csv")
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    rows = []
    for number, line in enumerate(body.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        values = line.split(",")
        if len(values) != N_FEATURES:
            raise ValueError(f"Line {number}: expected {N_FEATURES} values, got {len(values)}")
        try:
            rows.append([float(v) for v in values])
        except ValueError:
            raise ValueError(f"Line {number}: all values must be numbers: {line!r}") from None
    if not rows:
        raise ValueError("Empty request")
    return np.array(rows)


def predict_fn(data, model):
    probabilities = model.predict_proba(data)
    labels = [str(c) for c in model.classes_]
    best = probabilities.argmax(axis=1)
    return [(labels[i], float(p[i])) for i, p in zip(best, probabilities)]


def output_fn(prediction, accept="text/csv"):
    return "\n".join(f"{label},{confidence:.3f}" for label, confidence in prediction) + "\n"
