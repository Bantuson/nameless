"""Pure vector-math tests — normalization, cosine, deterministic ranking."""

from __future__ import annotations

import numpy as np
import pytest

from nameless_workers.pure.vectors import cosine_similarity, l2_normalize, rank_by_cosine


def test_l2_normalize_gives_unit_length():
    v = l2_normalize([3.0, 4.0])
    assert np.linalg.norm(v) == pytest.approx(1.0)
    assert v.tolist() == pytest.approx([0.6, 0.8])


def test_l2_normalize_zero_vector_is_unchanged():
    v = l2_normalize([0.0, 0.0, 0.0])
    assert v.tolist() == [0.0, 0.0, 0.0]


def test_cosine_identity_and_orthogonality():
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)


def test_cosine_zero_vector_is_zero():
    assert cosine_similarity([0, 0], [1, 1]) == 0.0


def test_rank_orders_by_similarity_descending():
    query = [1.0, 0.0]
    candidates = [
        ("orthogonal", [0.0, 1.0]),
        ("same", [1.0, 0.0]),
        ("close", [0.9, 0.1]),
        ("opposite", [-1.0, 0.0]),
    ]
    ranked = rank_by_cosine(query, candidates, limit=10)
    ids = [cid for cid, _ in ranked]
    assert ids == ["same", "close", "orthogonal", "opposite"]
    # scores are sorted descending
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_respects_limit_and_is_stable_on_ties():
    query = [1.0, 0.0]
    # Two candidates with identical direction → identical score → input order preserved (stable).
    candidates = [("a", [2.0, 0.0]), ("b", [5.0, 0.0]), ("c", [0.0, 1.0])]
    ranked = rank_by_cosine(query, candidates, limit=2)
    assert [cid for cid, _ in ranked] == ["a", "b"]


def test_rank_empty_and_zero_limit():
    assert rank_by_cosine([1.0], [], limit=5) == []
    assert rank_by_cosine([1.0], [("a", [1.0])], limit=0) == []
