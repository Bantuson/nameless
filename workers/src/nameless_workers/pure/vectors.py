"""Vector math for embeddings — pure functions used by retrieval and by the fake repo.

CLAP vectors are *direction*-meaningful, not magnitude-meaningful: two clips are "similar" when their
embeddings point the same way, regardless of length. So we L2-normalize and compare with cosine
similarity. After normalization, cosine similarity equals the dot product and equals
``1 - cosine_distance`` (pgvector's ``<=>`` operator), so the in-memory fake and the Postgres adapter
rank identically — which is exactly what makes the fake a faithful test double for retrieval.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def l2_normalize(v: Sequence[float]) -> np.ndarray:
    """Return ``v`` scaled to unit L2 norm. A zero vector is returned unchanged (norm stays 0)."""
    arr = np.asarray(v, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return arr
    return arr / norm


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [−1, 1]. Returns 0.0 if either vector is all-zero (undefined direction)."""
    av = np.asarray(a, dtype=np.float64)
    bv = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(av))
    nb = float(np.linalg.norm(bv))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(av, bv) / (na * nb))


def rank_by_cosine(
    query: Sequence[float],
    candidates: Sequence[tuple[object, Sequence[float]]],
    limit: int,
) -> list[tuple[object, float]]:
    """Rank ``candidates`` (``(id, vector)`` pairs) by cosine similarity to ``query``, descending.

    Returns the top ``limit`` as ``(id, score)`` pairs. Ties are broken by the candidates' original
    order (numpy's stable argsort), so results are deterministic — essential for a testable ranking.
    """
    if limit <= 0 or not candidates:
        return []
    q = np.asarray(query, dtype=np.float64)
    scores = np.array([cosine_similarity(q, vec) for _, vec in candidates], dtype=np.float64)
    # Descending by score; stable so equal scores keep input order.
    order = np.argsort(-scores, kind="stable")[:limit]
    return [(candidates[i][0], float(scores[i])) for i in order]
