"""Shared test fixtures + helpers. Everything runs against the FAKES (pydantic + stdlib only).

No yt-dlp / youtube-transcript-api / faster-whisper is importable on the base env, and nothing here
imports them — the real adapters keep those imports lazy inside methods. The whole suite exercises the
real control flow (pure core + orchestration + the REAL sqlite store) with only the network/ASR leaves
swapped for deterministic fakes + a virtual clock.
"""

from __future__ import annotations

import random

import pytest

from knowledge_pipeline.adapters import (
    FakeClock,
    FixedTextTranscriber,
    FixtureDiscoverySource,
    FixtureTranscriptFetcher,
    InMemoryCorpusStore,
    IntervalRateLimiter,
)
from knowledge_pipeline.domain.models import (
    CaptionSource,
    RawTranscript,
    TranscriptSegment,
)
from knowledge_pipeline.fixtures import load_fixture_corpus
from knowledge_pipeline.pipeline import IngestPipeline, PipelineConfig


def make_transcript(
    *,
    video_id: str = "vid",
    caption_source: CaptionSource = CaptionSource.MANUAL,
    segments: list[tuple[float, float, str]] | None = None,
    language: str = "en",
) -> RawTranscript:
    """Build a RawTranscript from (start_s, duration_s, text) triples."""
    segs = segments if segments is not None else [(0.0, 5.0, "high pass the bass around 30 hz")]
    return RawTranscript(
        video_id=video_id,
        caption_source=caption_source,
        language=language,
        fetched_via="test",
        segments=[TranscriptSegment(start_s=s, duration_s=d, text=t) for (s, d, t) in segs],
    )


@pytest.fixture
def fixture_corpus():
    return load_fixture_corpus()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fixture_pipeline(fixture_corpus, fake_clock):
    """A pipeline wired entirely over fakes + the in-memory store + a throttle on the FAKE clock.

    Using a real IntervalRateLimiter on the FakeClock means the pipeline genuinely throttles — and the
    test can assert the virtual time spent — without any real sleeping.
    """
    store = InMemoryCorpusStore()
    limiter = IntervalRateLimiter(fake_clock, min_interval_s=2.0, jitter_s=0.0, rng=random.Random(0))
    pipeline = IngestPipeline(
        discovery=FixtureDiscoverySource(fixture_corpus.videos),
        fetcher=FixtureTranscriptFetcher(fixture_corpus.fetches),
        transcriber=FixedTextTranscriber(fixture_corpus.asr),
        store=store,
        rate_limiter=limiter,
        clock=fake_clock,
        config=PipelineConfig(results_per_query=5),
    )
    return pipeline, store, fake_clock
