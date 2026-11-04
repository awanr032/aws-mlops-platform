import os
import re
import sys
import zlib

import numpy as np
import pytest

HERE = os.path.dirname(__file__)
PROJECT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(PROJECT, "rag"))
sys.path.insert(0, os.path.join(PROJECT, "eval"))
MANUALS = os.path.join(PROJECT, "manuals")


def fake_embed(text: str, dims: int = 512) -> list[float]:
    """Stand-in for Bedrock: counts words into buckets. Captures shared words, not meaning,
    which is enough to test the plumbing (chunk → index → search) without AWS."""
    vector = np.zeros(dims, dtype="float32")
    for word in re.findall(r"[a-z0-9\-\.]+", text.lower()):
        if len(word) > 2:
            vector[zlib.crc32(word.encode()) % dims] += 1
    return vector.tolist()


@pytest.fixture(scope="session")
def manuals():
    found = {}
    for name in sorted(os.listdir(MANUALS)):
        with open(os.path.join(MANUALS, name), encoding="utf-8") as f:
            found[f"manuals/{name}"] = (f.read(), f"etag-{name}")
    return found


@pytest.fixture(scope="session")
def built(manuals):
    import indexer

    return indexer.build(manuals, fake_embed, "test-build")
