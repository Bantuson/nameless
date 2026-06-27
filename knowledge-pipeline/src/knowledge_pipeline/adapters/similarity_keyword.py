"""KeywordSimilarityIndex — the stdlib :class:`~knowledge_pipeline.ports.SimilarityIndex` fake.

Token-set Jaccard over :func:`knowledge_pipeline.domain.keys.tokens` — no model, no install, deterministic.
It is the default semantic-dedup hook: good enough to collapse same-source near-paraphrases ("roll off the
low end" vs "roll off the bottom end") while keeping the core fully testable. The real, embedding-backed
:class:`~knowledge_pipeline.adapters.similarity_embeddings.EmbeddingSimilarityIndex` satisfies the same
``similarity(a, b) -> float`` seam and drops in unchanged when stronger paraphrase detection is wanted.
"""

from __future__ import annotations

from ..domain.keys import tokens


class KeywordSimilarityIndex:
    """Jaccard token similarity (0..1). Pure, deterministic, dependency-free."""

    def similarity(self, a: str, b: str) -> float:
        ta, tb = set(tokens(a)), set(tokens(b))
        if not ta and not tb:
            return 1.0
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        union = len(ta | tb)
        return inter / union if union else 0.0
