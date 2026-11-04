"""The vector index: FAISS for "find the nearest chunks", JSON for the chunk texts.

Vectors are normalised to length 1, so the inner product FAISS computes is the cosine
similarity: 1.0 = same meaning, around 0 = unrelated. IndexFlatIP compares the question with
every chunk (exact search); that takes microseconds for thousands of chunks. For millions,
switch to an approximate index such as HNSW.
"""

from __future__ import annotations

import json
import os

import faiss
import numpy as np

INDEX_FILE, CHUNKS_FILE = "faiss.index", "chunks.json"


def normalise(vectors) -> np.ndarray:
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr[None, :]
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.where(norms == 0, 1, norms)


class VectorStore:
    def __init__(self, index, chunks: list[dict]):
        if index.ntotal != len(chunks):
            raise ValueError(f"index has {index.ntotal} vectors but there are {len(chunks)} chunks")
        self.index, self.chunks = index, chunks

    @classmethod
    def build(cls, vectors, chunks: list[dict]) -> "VectorStore":
        arr = normalise(vectors)
        index = faiss.IndexFlatIP(arr.shape[1])
        index.add(arr)
        return cls(index, chunks)

    @property
    def dimensions(self) -> int:
        return self.index.d

    def search(self, vector, k: int = 4) -> list[tuple[dict, float]]:
        query = normalise(vector)
        if query.shape[1] != self.dimensions:
            raise ValueError(f"query has {query.shape[1]} dimensions, index has {self.dimensions}")
        scores, ids = self.index.search(query, min(k, len(self.chunks)))
        return [(self.chunks[i], round(float(s), 4)) for i, s in zip(ids[0], scores[0]) if i >= 0]

    def save(self, folder: str) -> None:
        os.makedirs(folder, exist_ok=True)
        faiss.write_index(self.index, os.path.join(folder, INDEX_FILE))
        with open(os.path.join(folder, CHUNKS_FILE), "w") as f:
            json.dump(self.chunks, f)

    @classmethod
    def load(cls, folder: str) -> "VectorStore":
        index = faiss.read_index(os.path.join(folder, INDEX_FILE))
        with open(os.path.join(folder, CHUNKS_FILE)) as f:
            return cls(index, json.load(f))
