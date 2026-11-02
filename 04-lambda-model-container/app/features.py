"""Checks on prediction requests. No ML or AWS code here."""

from __future__ import annotations

import math

FEATURES = ["rms", "kurtosis", "crest_factor", "peak_freq_hz", "shaft_speed_hz"]
RANGES = {
    "rms": (0.0, 50.0),
    "kurtosis": (0.0, 100.0),
    "crest_factor": (1.0, 50.0),
    "peak_freq_hz": (0.0, 20000.0),
    "shaft_speed_hz": (1.0, 500.0),
}
MAX_BATCH = 100


class BadRequest(Exception):
    pass


def parse_reading(reading, position: str = "") -> list[float]:
    """Turn one reading into a feature row in the model's column order."""
    where = f" in {position}" if position else ""
    if not isinstance(reading, dict):
        raise BadRequest(f"each reading must be a JSON object{where}")
    missing = [f for f in FEATURES if f not in reading]
    if missing:
        raise BadRequest(f"missing {', '.join(missing)}{where}")

    row = []
    for name in FEATURES:
        value = reading[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise BadRequest(f"{name} must be a number{where}")
        low, high = RANGES[name]
        if not low <= value <= high:
            raise BadRequest(f"{name}={value} is outside the plausible range {low}-{high}{where}")
        row.append(float(value))
    return row


def parse_request(event) -> tuple[list[list[float]], bool]:
    """Accept one reading, or {"readings": [...]} for a batch. Returns (rows, is_batch)."""
    if isinstance(event, dict) and "readings" in event:
        readings = event["readings"]
        if not isinstance(readings, list) or not readings:
            raise BadRequest("'readings' must be a non-empty list")
        if len(readings) > MAX_BATCH:
            raise BadRequest(f"at most {MAX_BATCH} readings per request")
        return [parse_reading(r, f"readings[{i}]") for i, r in enumerate(readings)], True
    return [parse_reading(event)], False
