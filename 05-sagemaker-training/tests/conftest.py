import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "training"))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))


@pytest.fixture(scope="session")
def channels(tmp_path_factory):
    """Lay out folders exactly as SageMaker does: one folder per input channel, plus the model folder."""
    import common
    from data import FEATURES, generate

    root = tmp_path_factory.mktemp("opt_ml")
    for name, n, seed in [("train", 300, 42), ("test", 100, 7)]:
        X, y = generate(n_per_class=n, seed=seed)
        rows = [[label, *(round(float(v), 4) for v in f)] for f, label in zip(X, y)]
        folder = root / "input" / "data" / name
        folder.mkdir(parents=True)
        (folder / f"{name}.csv").write_text(common.to_csv(["condition", *FEATURES], rows))
    (root / "model").mkdir()
    return root


@pytest.fixture(scope="session")
def model_dir(channels):
    import train

    args = ["--train", str(channels / "input/data/train"), "--test", str(channels / "input/data/test"),
            "--model-dir", str(channels / "model"), "--n-estimators", "60"]
    assert train.main(args) == 0
    return str(channels / "model")
