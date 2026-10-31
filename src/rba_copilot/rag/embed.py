"""Local sentence embeddings. CPU only, no paid API."""

from __future__ import annotations

import os

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def model_name() -> str:
    return os.environ.get("RBA_EMBED_MODEL", DEFAULT_MODEL)


def encode(texts: list[str], batch_size: int = 64) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name(), device="cpu")
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return np.asarray(vectors, dtype=np.float32)
