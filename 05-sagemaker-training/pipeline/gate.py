"""The quality gate: decides whether a trained model is Approved or Rejected in the registry.

Same rule as project 04: overall accuracy must reach the minimum, and no single fault type
may be much worse (a model can look accurate overall while missing one fault entirely).
"""

from __future__ import annotations

MIN_ACCURACY = 0.90
RECALL_SLACK = 0.10  # each class's recall must be at least MIN_ACCURACY - 0.10


def check(metrics: dict, min_accuracy: float = MIN_ACCURACY) -> tuple[bool, list[str]]:
    """Return (passed, reasons). Reasons explain every failure, or say why it passed."""
    problems = []
    accuracy = metrics.get("accuracy")
    recalls = metrics.get("recall_per_class") or {}
    if accuracy is None or not recalls:
        return False, ["metrics.json is missing accuracy or per-class recall"]
    if accuracy < min_accuracy:
        problems.append(f"accuracy {accuracy:.3f} is below {min_accuracy:.2f}")
    min_recall = min_accuracy - RECALL_SLACK
    for label, recall in sorted(recalls.items()):
        if recall < min_recall:
            problems.append(f"recall for {label} is {recall:.3f}, below {min_recall:.2f}")
    if problems:
        return False, problems
    return True, [f"accuracy {accuracy:.3f}, lowest class recall {min(recalls.values()):.3f}"]
