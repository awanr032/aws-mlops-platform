import json
import os

from data import CLASSES, FEATURES, generate
from train import gate, train_and_evaluate


def test_data_is_reproducible_and_balanced():
    X1, y1 = generate(n_per_class=50, seed=7)
    X2, y2 = generate(n_per_class=50, seed=7)
    assert (X1 == X2).all() and y1 == y2
    assert X1.shape == (200, len(FEATURES))
    assert {c: y1.count(c) for c in CLASSES} == {c: 50 for c in CLASSES}


def test_fault_frequencies_follow_shaft_speed():
    X, y = generate(n_per_class=200, seed=1)
    peak, shaft = X[:, 3], X[:, 4]
    ratios = {c: (peak / shaft)[[i for i, label in enumerate(y) if label == c]].mean() for c in CLASSES}
    assert ratios["ball_fault"] < ratios["outer_race_fault"] < ratios["inner_race_fault"]


def test_trained_model_passes_the_gate():
    _, metrics = train_and_evaluate(n_per_class=300)
    assert gate(metrics, 0.90) == []


def test_gate_blocks_low_accuracy():
    metrics = {"accuracy": 0.85, "recall_per_class": {c: 0.9 for c in CLASSES}}
    assert gate(metrics, 0.90) == ["accuracy 0.850 is below 0.900"]


def test_gate_blocks_a_model_that_misses_one_fault_type():
    recalls = {c: 0.99 for c in CLASSES}
    recalls["outer_race_fault"] = 0.70
    problems = gate({"accuracy": 0.93, "recall_per_class": recalls}, 0.90)
    assert problems == ["recall for outer_race_fault is only 0.700"]


def test_training_writes_model_and_metrics(model_dir):
    assert os.path.exists(os.path.join(model_dir, "model.joblib"))
    with open(os.path.join(model_dir, "metrics.json")) as f:
        metrics = json.load(f)
    assert metrics["features"] == FEATURES
    assert metrics["accuracy"] >= 0.90
