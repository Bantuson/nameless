"""snapshot_record tests (KNOW-02) — content hash + injected retrieval date + citation anchors."""

from __future__ import annotations

import datetime as _dt

from knowledge_pipeline.domain.models import CaptionSource
from knowledge_pipeline.pure.snapshot import content_hash, snapshot_record

from .conftest import make_transcript

NOW = _dt.datetime(2026, 6, 27, 9, 30, 0, tzinfo=_dt.timezone.utc)

SEGS = [
    (8.0, 4.0, "high pass the log drum around 40 hz"),
    (13.0, 5.0, "sidechain the bass to the kick"),
]


def test_retrieval_date_is_the_injected_now():
    t = make_transcript(segments=SEGS)
    rec = snapshot_record(t, NOW)
    assert rec.retrieval_date == NOW  # never the wall clock — exactly what we passed


def test_hash_is_deterministic_for_identical_content():
    t1 = make_transcript(video_id="v", segments=SEGS)
    t2 = make_transcript(video_id="v", segments=SEGS)
    assert content_hash(t1) == content_hash(t2)
    assert snapshot_record(t1, NOW).content_sha256 == snapshot_record(t2, NOW).content_sha256


def test_hash_changes_when_text_changes():
    base = make_transcript(video_id="v", segments=SEGS)
    drifted = make_transcript(
        video_id="v",
        segments=[(8.0, 4.0, "high pass the log drum around 30 hz"), (13.0, 5.0, "sidechain the bass to the kick")],
    )
    assert content_hash(base) != content_hash(drifted)  # a re-caption is detectable drift


def test_hash_ignores_fetch_path():
    # The same captions pulled by two different tools must snapshot to the SAME content hash.
    via_api = make_transcript(video_id="v", segments=SEGS)
    via_api = via_api.model_copy(update={"fetched_via": "youtube-transcript-api"})
    via_ytdlp = make_transcript(video_id="v", segments=SEGS).model_copy(update={"fetched_via": "yt-dlp-subs"})
    assert content_hash(via_api) == content_hash(via_ytdlp)


def test_record_keeps_segment_span_for_citation():
    t = make_transcript(segments=SEGS)
    rec = snapshot_record(t, NOW)
    assert rec.first_segment_s == 8.0
    assert rec.last_segment_s == 13.0
    assert rec.segment_count == 2
    assert rec.char_count == len(t.full_text())
    assert rec.caption_source is CaptionSource.MANUAL


def test_empty_transcript_snapshots_without_span():
    t = make_transcript(caption_source=CaptionSource.NONE, segments=[])
    rec = snapshot_record(t, NOW)
    assert rec.segment_count == 0
    assert rec.first_segment_s is None and rec.last_segment_s is None
    assert len(rec.content_sha256) == 64  # still a valid sha256 hex of the (empty) canonical payload
