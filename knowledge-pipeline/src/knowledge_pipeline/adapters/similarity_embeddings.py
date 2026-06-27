"""EmbeddingSimilarityIndex — the REAL embedding-backed :class:`~knowledge_pipeline.ports.SimilarityIndex`.

Cosine similarity over sentence embeddings, for stronger semantic dedup than keyword Jaccard ("high-pass
the bottom" ≈ "roll off the low end" even with no shared tokens). Satisfies the same ``similarity(a, b)``
seam as the keyword fake, so it is an opt-in upgrade — the pure core never depends on it.

ENV-GATED / NOT RUN HERE: ``sentence_transformers`` (+ torch) is a heavy import done LAZILY in ``__init__``
and the package never imports this module eagerly, so the base install stays light. Running it needs
``uv sync --extra embed`` and model weights. Embeddings are normalized so cosine == dot product.
"""

from __future__ import annotations

from functools import lru_cache


class EmbeddingSimilarityIndex:
    """Cosine similarity over a sentence-embedding model. Heavy import is LAZY; env-gated."""

    def __init__(self, *, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        # LAZY heavy import — keeps the package importable on the base env.
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model = SentenceTransformer(model_name)

    @lru_cache(maxsize=4096)
    def _embed(self, text: str):
        # normalize_embeddings=True => cosine similarity is a plain dot product.
        return self._model.encode(text, normalize_embeddings=True)

    def similarity(self, a: str, b: str) -> float:
        va, vb = self._embed(a), self._embed(b)
        return float(sum(x * y for x, y in zip(va, vb)))
