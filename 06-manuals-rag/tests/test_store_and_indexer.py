import numpy as np
import pytest

from conftest import fake_embed
from store import VectorStore


def test_manifest_describes_the_build(built, manuals):
    store, manifest = built
    assert manifest["build_id"] == "test-build"
    assert manifest["chunks"] == len(store.chunks) == store.index.ntotal
    assert manifest["manuals"] == {k: etag for k, (_t, etag) in manuals.items()}
    assert set(manifest["chunks_per_manual"]) == set(manuals)
    assert len({c["id"] for c in store.chunks}) == len(store.chunks)  # ids are unique


@pytest.mark.parametrize("question, source, section", [
    ("P-200 bearing housing bolts torque", "p200-centrifugal-pump", "6.3 Bearing housing"),
    ("G-40 output coupling bolts torque", "g40-helical-gearbox", "3 Installation"),
    ("C-75 air filter element replace hours", "c75-screw-compressor", "5 Air filter"),
])
def test_search_finds_the_right_section(built, question, source, section):
    store, _ = built
    hits = store.search(fake_embed(question), k=3)
    # The word-counting stand-in has no sense of meaning, so "in the top 3" is the fair test here;
    # the real Bedrock embeddings are checked by eval/run_eval.py against the live system.
    assert (source, section) in [(c["source"], c["section"]) for c, _ in hits]
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)  # best first


def test_scores_are_cosine_similarities(built):
    store, _ = built
    chunk = store.chunks[3]
    from chunking import embedding_text

    (top, score), *_ = store.search(fake_embed(embedding_text(chunk)), k=1)
    assert top["id"] == chunk["id"] and score == pytest.approx(1.0, abs=1e-4)


def test_save_and_load_round_trip(built, tmp_path):
    store, _ = built
    store.save(str(tmp_path))
    loaded = VectorStore.load(str(tmp_path))
    query = fake_embed("pump vibration limits trip")
    assert loaded.search(query, 3) == store.search(query, 3)


def test_wrong_dimensions_rejected(built):
    store, _ = built
    with pytest.raises(ValueError, match="dimensions"):
        store.search(np.ones(10), 2)


def test_k_larger_than_index_is_fine():
    store = VectorStore.build([[1, 0], [0, 1]], [{"id": "a"}, {"id": "b"}])
    assert len(store.search([1, 0], 8)) == 2


def test_empty_manuals_rejected():
    import indexer

    with pytest.raises(ValueError):
        indexer.build({"manuals/empty.md": ("", "e")}, fake_embed, "b")
