"""IngestPipeline end-to-end tests over the fixture corpus (KNOW-01..04), all on fakes + a virtual clock.

Proves the full flow works without any network/ASR/real-time: discover -> dedup -> fetch+fallback ->
(ASR on the right branch) -> snapshot -> score -> register, plus idempotent re-runs and a real throttle.
"""

from __future__ import annotations

import random

from knowledge_pipeline.adapters import (
    FakeClock,
    FixedTextTranscriber,
    FixtureDiscoverySource,
    FixtureTranscriptFetcher,
    InMemoryCorpusStore,
    IntervalRateLimiter,
)
from knowledge_pipeline.domain.models import CaptionSource, IngestStatus, Verdict
from knowledge_pipeline.fixtures import load_fixture_corpus
from knowledge_pipeline.pipeline import IngestPipeline, PipelineConfig
from knowledge_pipeline.pure.query_grid import query_grid


def _build():
    corpus = load_fixture_corpus()
    clock = FakeClock()
    fetcher = FixtureTranscriptFetcher(corpus.fetches)
    transcriber = FixedTextTranscriber(corpus.asr)
    store = InMemoryCorpusStore()
    pipeline = IngestPipeline(
        discovery=FixtureDiscoverySource(corpus.videos),
        fetcher=fetcher,
        transcriber=transcriber,
        store=store,
        rate_limiter=IntervalRateLimiter(clock, min_interval_s=2.0, jitter_s=0.0, rng=random.Random(0)),
        clock=clock,
        config=PipelineConfig(results_per_query=5),
    )
    return pipeline, store, fetcher, transcriber, clock, corpus


def test_discovery_finds_and_dedups_fixture_videos():
    pipeline, *_ = _build()
    videos = pipeline.discover(query_grid())
    ids = {v.video_id for v in videos}
    # every fixture video is discoverable through the north-star grid / anchors …
    assert ids == {
        "amapiano_drums_rich",
        "deephouse_bass_auto_good",
        "rnb_vocal_no_captions",
        "altpiano_visual_only",
        "amapiano_mixing_auto_noisy",
        "deephouse_atmosphere_sparse",
    }
    # … and dedup collapsed the many overlapping query hits to unique videos.
    assert len(videos) == len(ids)
    # provenance merge: a video surfaced by several queries records all of them.
    drums = next(v for v in videos if v.video_id == "amapiano_drums_rich")
    assert "," in (drums.query_origin or "")


def test_full_ingest_processes_every_video_once():
    pipeline, store, *_ = _build()
    report = pipeline.run(query_grid())
    assert report.ingested + report.rejected == 6
    assert report.errored == 0
    assert report.skipped == 0
    assert store.stats().total == 6


def test_caption_paths_select_the_right_source():
    pipeline, store, fetcher, transcriber, _clock, _corpus = _build()
    pipeline.run(query_grid())

    # manual captions used as-is
    assert store.get("amapiano_drums_rich").snapshot.caption_source is CaptionSource.MANUAL
    # good auto captions used as-is (NO ASR)
    assert store.get("deephouse_bass_auto_good").snapshot.caption_source is CaptionSource.AUTO
    assert "deephouse_bass_auto_good" not in transcriber.calls
    # no captions ⇒ ASR fallback fired
    assert store.get("rnb_vocal_no_captions").snapshot.caption_source is CaptionSource.ASR
    assert "rnb_vocal_no_captions" in transcriber.calls
    # noisy auto captions ⇒ ASR re-transcribe fired
    assert store.get("amapiano_mixing_auto_noisy").snapshot.caption_source is CaptionSource.ASR
    assert "amapiano_mixing_auto_noisy" in transcriber.calls


def test_extractability_verdicts_are_honest():
    pipeline, store, *_ = _build()
    pipeline.run(query_grid())

    # rich, parameterized tutorial keeps
    assert store.get("amapiano_drums_rich").extractability.verdict is Verdict.KEEP
    # ASR-recovered vocal-layering lesson keeps
    assert store.get("rnb_vocal_no_captions").extractability.verdict is Verdict.KEEP
    # the visual-only "as you can see... boom" tutorial is flagged and NOT kept (the whole point)
    visual = store.get("altpiano_visual_only").extractability
    assert "visual_only" in visual.flags
    assert visual.verdict is not Verdict.KEEP
    # the sparse vlog is low-signal/rejected, not promoted to teachable craft
    sparse = store.get("deephouse_atmosphere_sparse").extractability
    assert sparse.verdict in (Verdict.LOW_SIGNAL, Verdict.REJECT)


def test_asr_not_invoked_when_usable_captions_exist():
    pipeline, _store, _fetcher, transcriber, *_ = _build()
    pipeline.run(query_grid())
    # manual + good-auto + sparse-manual videos must NOT have hit ASR (GPU cost discipline)
    for vid in ("amapiano_drums_rich", "deephouse_bass_auto_good", "altpiano_visual_only", "deephouse_atmosphere_sparse"):
        assert vid not in transcriber.calls


def test_snapshot_segments_survive_for_citation():
    pipeline, store, *_ = _build()
    pipeline.run(query_grid())
    snap = store.load_snapshot("amapiano_drums_rich")
    assert snap is not None
    assert len(snap.segments) >= 4
    # every segment carries a timestamp ⇒ Phase 4 can cite `video_id @ ts`
    assert all(seg.start_s >= 0 for seg in snap.segments)


def test_reingest_is_idempotent():
    pipeline, store, *_ = _build()
    first = pipeline.run(query_grid())
    assert first.skipped == 0
    second = pipeline.run(query_grid())
    # nothing re-fetched; everything already in the corpus
    assert second.ingested == 0 and second.rejected == 0
    assert second.skipped == 6
    assert store.stats().total == 6  # no duplicates created


def test_throttle_actually_spaced_requests_in_virtual_time():
    pipeline, _store, _fetcher, _transcriber, clock, _corpus = _build()
    pipeline.run(query_grid())
    # many discovery queries + per-video fetches + ASR pulls ⇒ substantial virtual time spent throttling,
    # with zero real sleep (the FakeClock advanced instead of blocking).
    assert clock.total_slept > 0.0


def test_registry_inspectable_by_genre_and_extractability():
    # KNOW-04: the corpus is inspectable by genre + extractability concentration.
    pipeline, store, *_ = _build()
    pipeline.run(query_grid())

    amapiano = store.list_entries(genre="amapiano")
    assert {e.video.video_id for e in amapiano} == {"amapiano_drums_rich", "amapiano_mixing_auto_noisy"}

    by_score = store.list_entries(order_by_score=True)
    scores = [e.extractability.score for e in by_score]
    assert scores == sorted(scores, reverse=True)

    keeps = store.list_entries(verdict=Verdict.KEEP)
    assert all(e.extractability.verdict is Verdict.KEEP for e in keeps)


def test_no_asr_config_rejects_uncaptioned_video():
    # With ASR disabled, the no-captions video has nothing teachable ⇒ recorded as rejected, not faked.
    corpus = load_fixture_corpus()
    clock = FakeClock()
    store = InMemoryCorpusStore()
    pipeline = IngestPipeline(
        discovery=FixtureDiscoverySource(corpus.videos),
        fetcher=FixtureTranscriptFetcher(corpus.fetches),
        transcriber=FixedTextTranscriber(corpus.asr),
        store=store,
        rate_limiter=IntervalRateLimiter(clock, min_interval_s=0.0),
        clock=clock,
        config=PipelineConfig(results_per_query=5, asr_enabled=False),
    )
    pipeline.run(query_grid())
    entry = store.get("rnb_vocal_no_captions")
    assert entry is not None
    assert entry.extractability.verdict is Verdict.REJECT
    assert entry.snapshot.caption_source is CaptionSource.NONE
