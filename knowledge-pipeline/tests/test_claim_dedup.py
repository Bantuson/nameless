"""dedup_claims — distinct sources, not repeats (KNOW-06). Cross-source claims are never merged."""

from __future__ import annotations

from knowledge_pipeline.adapters import KeywordSimilarityIndex
from knowledge_pipeline.pure.claim_dedup import dedup_claims

from .conftest import make_claim


def test_exact_id_duplicate_is_dropped():
    c = make_claim(video="v", ts_ms=8000, claim_text="High-pass the sub around 30 Hz.")
    dup = make_claim(video="v", ts_ms=8000, claim_text="high-pass the sub around 30 hz")  # same id
    deduped, dropped = dedup_claims([c, dup])
    assert len(deduped) == 1
    assert dropped == 1


def test_same_source_same_topic_same_text_collapsed():
    a = make_claim(video="v", ts_ms=1000, claim_text="Roll off the low end.")
    b = make_claim(video="v", ts_ms=9000, claim_text="roll off the low end")  # same source+topic+text, new ts
    deduped, dropped = dedup_claims([a, b])
    assert len(deduped) == 1
    assert dropped == 1


def test_distinct_sources_are_never_merged():
    a = make_claim(video="v1", ts_ms=1000, claim_text="Roll off the low end.")
    b = make_claim(video="v2", ts_ms=1000, claim_text="Roll off the low end.")  # different source!
    deduped, dropped = dedup_claims([a, b])
    assert len(deduped) == 2          # cross-source agreement is signal, not a duplicate
    assert dropped == 0


def test_semantic_dedup_collapses_same_source_paraphrase_only_when_enabled():
    a = make_claim(video="v", ts_ms=1000, claim_text="roll off the low end of the sub")
    b = make_claim(video="v", ts_ms=9000, claim_text="roll off the low end")  # high keyword overlap

    no_sem, _ = dedup_claims([a, b])
    assert len(no_sem) == 2           # different exact text -> kept without the semantic hook

    sim = KeywordSimilarityIndex().similarity
    with_sem, dropped = dedup_claims([a, b], similarity=sim, threshold=0.5)
    assert len(with_sem) == 1 and dropped == 1


def test_semantic_dedup_does_not_merge_across_sources():
    a = make_claim(video="v1", ts_ms=1000, claim_text="roll off the low end of the sub")
    b = make_claim(video="v2", ts_ms=1000, claim_text="roll off the low end")
    sim = KeywordSimilarityIndex().similarity
    deduped, dropped = dedup_claims([a, b], similarity=sim, threshold=0.3)
    assert len(deduped) == 2 and dropped == 0
