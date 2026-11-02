import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, os.path.join(HERE, "..", "training"))


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    """Train a small model once for the whole test run and point the handler at it."""
    import train

    out = tmp_path_factory.mktemp("model")
    assert train.main(["--out", str(out), "--rows-per-class", "300"]) == 0
    return str(out)
