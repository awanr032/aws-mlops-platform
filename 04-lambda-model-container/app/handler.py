"""Lambda entry point: predict bearing condition from vibration features.

The model is loaded once per container (on the first request after a cold start)
and reused for every later request, which is what makes warm requests fast.
"""

from __future__ import annotations

import json
import logging
import os
import time

from features import BadRequest, parse_request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(os.path.dirname(__file__), "model"))

_model = None
_metrics = None
_load_ms = None


def _load():
    global _model, _metrics, _load_ms
    if _model is None:
        import joblib

        started = time.perf_counter()
        _model = joblib.load(os.path.join(MODEL_DIR, "model.joblib"))
        _model.n_jobs = 1  # one small request at a time: skip the thread-pool overhead
        with open(os.path.join(MODEL_DIR, "metrics.json")) as f:
            _metrics = json.load(f)
        _load_ms = round((time.perf_counter() - started) * 1000)
        logger.info(json.dumps({"event": "model_loaded", "load_ms": _load_ms}))
    return _model, _metrics


def lambda_handler(event, context):
    started = time.perf_counter()
    cold = _model is None
    try:
        rows, is_batch = parse_request(event)
    except BadRequest as exc:
        return {"error": str(exc)}

    model, metrics = _load()
    probabilities = model.predict_proba(rows)
    labels = [str(c) for c in model.classes_]

    predictions = []
    for probs in probabilities:
        best = max(range(len(labels)), key=lambda i: probs[i])
        predictions.append({
            "condition": labels[best],
            "confidence": round(float(probs[best]), 3),
            "probabilities": {label: round(float(p), 3) for label, p in zip(labels, probs)},
        })

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(json.dumps({"event": "predict", "rows": len(rows), "cold_start": cold, "ms": elapsed_ms}))

    response = {
        "model": {
            "version": os.environ.get("MODEL_VERSION", "local"),
            "trained_accuracy": metrics["accuracy"],
        },
        "cold_start": cold,
        "elapsed_ms": elapsed_ms,
    }
    if cold:
        response["model_load_ms"] = _load_ms
    if is_batch:
        response["predictions"] = predictions
    else:
        response["prediction"] = predictions[0]
    return response
