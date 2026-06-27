"""dedup tests (KNOW-01 dedup + KNOW-02 idempotency)."""

from __future__ import annotations

from knowledge_pipeline.domain.models import VideoRef
from knowledge_pipeline.pure.dedup import dedup_already_ingested, dedup_video_refs


def _v(video_id: str, *, origin: str = "", genre: str | None = None, stage: str | None = None) -> VideoRef:
    return VideoRef(video_id=video_id, title=f"title {video_id}", query_origin=origin, genre=genre, stage=stage)


def test_dedup_collapses_repeated_video_ids():
    refs = [_v("a", origin="q1"), _v("b", origin="q2"), _v("a", origin="q3")]
    unique, dupes = dedup_video_refs(refs)
    assert [r.video_id for r in unique] == ["a", "b"]
    assert dupes == 1


def test_dedup_merges_query_provenance():
    refs = [_v("a", origin="amapiano drums tutorial"), _v("a", origin="Lowbass Djy log drum")]
    unique, _ = dedup_video_refs(refs)
    assert len(unique) == 1
    merged = unique[0].query_origin
    assert "amapiano drums tutorial" in merged and "Lowbass Djy log drum" in merged


def test_dedup_backfills_missing_provenance_fields():
    refs = [_v("a", origin="q1", genre=None, stage=None), _v("a", origin="q2", genre="amapiano", stage="drums")]
    unique, _ = dedup_video_refs(refs)
    assert unique[0].genre == "amapiano"
    assert unique[0].stage == "drums"


def test_dedup_preserves_first_seen_order():
    refs = [_v("c"), _v("a"), _v("b"), _v("a")]
    unique, _ = dedup_video_refs(refs)
    assert [r.video_id for r in unique] == ["c", "a", "b"]


def test_already_ingested_are_dropped():
    refs = [_v("a"), _v("b"), _v("c")]
    fresh, skipped = dedup_already_ingested(refs, known_ids={"b"})
    assert [r.video_id for r in fresh] == ["a", "c"]
    assert skipped == 1


def test_already_ingested_empty_known_keeps_all():
    refs = [_v("a"), _v("b")]
    fresh, skipped = dedup_already_ingested(refs, known_ids=set())
    assert len(fresh) == 2 and skipped == 0
