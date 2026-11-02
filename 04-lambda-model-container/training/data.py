"""Synthetic bearing-vibration features for four conditions.

The numbers follow the textbook picture of rolling-element bearing faults:
  - damage makes the signal "spikier" (higher kurtosis and crest factor) and stronger (higher RMS)
  - each fault shows up at its own characteristic frequency, which scales with shaft speed:
      outer race (BPFO) ~ 3.6 x shaft speed, inner race (BPFI) ~ 5.4 x, ball (BSF) ~ 2.4 x
Shaft speed is an input because a fault frequency only means something relative to it:
an outer-race fault on a fast machine sits at the same Hz as an inner-race fault on a slow one.
Classes overlap on purpose, so the model has to learn rather than read off one number.
Swap this for a real dataset (e.g. the CWRU bearing data) without changing anything else.
"""

from __future__ import annotations

import numpy as np

FEATURES = ["rms", "kurtosis", "crest_factor", "peak_freq_hz", "shaft_speed_hz"]
CLASSES = ["healthy", "inner_race_fault", "outer_race_fault", "ball_fault"]

# (rms mean, rms sd), (kurtosis mean, sd), (crest mean, sd), frequency multiple of shaft speed
PROFILES = {
    "healthy":          ((0.30, 0.10), (3.0, 0.5), (3.5, 0.6), 1.0),
    "inner_race_fault": ((0.85, 0.25), (7.0, 1.6), (6.2, 1.0), 5.4),
    "outer_race_fault": ((0.70, 0.22), (6.0, 1.5), (5.6, 1.0), 3.6),
    "ball_fault":       ((0.50, 0.18), (4.6, 1.1), (4.6, 0.9), 2.4),
}


def generate(n_per_class: int = 1000, seed: int = 42):
    """Return (X, y): X is an (n, 5) float array in FEATURES order, y a list of class names."""
    rng = np.random.default_rng(seed)
    rows, labels = [], []
    for label in CLASSES:
        (rms_m, rms_s), (kurt_m, kurt_s), (crest_m, crest_s), multiple = PROFILES[label]
        shaft_hz = rng.uniform(20, 40, n_per_class)  # machines run at different speeds
        rms = np.clip(rng.normal(rms_m, rms_s, n_per_class), 0.05, None)
        kurtosis = np.clip(rng.normal(kurt_m, kurt_s, n_per_class), 1.5, None)
        crest = np.clip(rng.normal(crest_m, crest_s, n_per_class), 1.5, None)
        freq = shaft_hz * multiple * rng.normal(1.0, 0.04, n_per_class)  # slip and measurement error
        rows.append(np.column_stack([rms, kurtosis, crest, freq, shaft_hz]))
        labels += [label] * n_per_class
    return np.vstack(rows), labels
