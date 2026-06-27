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
    FakeClaimExtractor,
    FakeClock,
    FixedTextTranscriber,
    FixtureDiscoverySource,
    FixtureTranscriptFetcher,
    InMemoryClaimStore,
    InMemoryCorpusStore,
    IntervalRateLimiter,
    KeywordSimilarityIndex,
)
from knowledge_pipeline.claim_fixtures import load_claim_fixtures
from knowledge_pipeline.domain.claims import Claim
from knowledge_pipeline.domain.models import (
    CaptionSource,
    RawTranscript,
    TranscriptSegment,
)
from knowledge_pipeline.fixtures import load_fixture_corpus
from knowledge_pipeline.mining_pipeline import MineTarget, MiningPipeline
from knowledge_pipeline.pipeline import IngestPipeline, PipelineConfig
from knowledge_pipeline.pure.snapshot import snapshot_record


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


# ============================================================================================
# Phase-4 helpers (claim mining) — all over the fakes (pydantic + stdlib only).
# ============================================================================================


def make_claim(
    *,
    claim_text: str = "high-pass the sub bass around 30 hz",
    technique: str = "sub-bass-highpass",
    stage: str = "bassline",
    genre: list[str] | None = None,
    stance: str | None = None,
    confidence: float = 0.8,
    video: str = "vid1",
    ts_ms: int = 8000,
    quote: str | None = None,
    caption: CaptionSource = CaptionSource.MANUAL,
) -> Claim:
    """Build a Claim from sane defaults (quote defaults to claim_text so citation self-verifies)."""
    return Claim(
        claim_text=claim_text,
        technique=technique,
        stage=stage,
        genre=genre if genre is not None else ["deep-house"],
        stance=stance,
        confidence=confidence,
        source_video_id=video,
        timestamp_ms=ts_ms,
        quote=quote if quote is not None else claim_text,
        caption_source=caption,
    )


@pytest.fixture
def claim_corpus():
    """The bundled claim fixtures (consensus set + amapiano FLEX-vs-layered conflict)."""
    return load_claim_fixtures()


# ============================================================================================
# Phase-5 helpers (skill synthesis) — all over the fakes (pydantic + stdlib only).
# ============================================================================================

import datetime as _dt  # noqa: E402

from knowledge_pipeline.adapters import FakeSkillSynthesizer, InMemorySkillStore  # noqa: E402
from knowledge_pipeline.domain.skills import (  # noqa: E402
    ProductionCell,
    SectionKind,
    SkillCitation,
    SkillDraft,
    SkillSection,
)
from knowledge_pipeline.synthesis_pipeline import SynthesisPipeline  # noqa: E402

FIXED_NOW = _dt.datetime(2026, 6, 28, tzinfo=_dt.timezone.utc)


def mine_fixture_claim_layer():
    """Mine the bundled claim fixtures into (claim_store, corpus, snapshots) for Phase-5 tests.

    Reuses the Phase-4 mining flow over the fakes, so the Phase-5 input is the REAL cross-referenced
    consensus/conflict layer (not hand-built clusters) — the genuine extract->synthesize seam.
    """
    corpus = InMemoryCorpusStore()
    clock = FakeClock()
    snapshots: dict[str, RawTranscript] = {}
    claim_corpus = load_claim_fixtures()
    for vid, transcript in claim_corpus.transcripts.items():
        corpus.write_snapshot(transcript, snapshot_record(transcript, clock.now()))
        snapshots[vid] = transcript
    store = InMemoryClaimStore()
    MiningPipeline(
        FakeClaimExtractor(scripted=claim_corpus.scripted), store, corpus, similarity=KeywordSimilarityIndex()
    ).mine([MineTarget(video_id=v, genres=claim_corpus.genres.get(v, [])) for v in claim_corpus.video_ids])
    return store, corpus, snapshots


@pytest.fixture
def claim_layer():
    """``(claim_store, corpus, snapshots)`` — the mined Phase-4 layer Phase 5 synthesizes over."""
    return mine_fixture_claim_layer()


@pytest.fixture
def synthesis_plane(claim_layer):
    """A SynthesisPipeline wired over fakes: fake synthesizer + in-mem skill store + mined claim layer.

    Returns ``(pipeline, skill_store, claim_store, corpus)`` — drives select -> synthesize -> GATE ->
    emit -> store with no API, no tokens, no DB.
    """
    claim_store, corpus, _snapshots = claim_layer
    skill_store = InMemorySkillStore()
    pipeline = SynthesisPipeline(
        FakeSkillSynthesizer(), skill_store, claim_store, corpus=corpus, now=lambda: FIXED_NOW
    )
    return pipeline, skill_store, claim_store, corpus


def make_cell(stage: str = "bassline", genre: str = "deep-house") -> ProductionCell:
    return ProductionCell(stage=stage, genre=genre)


def make_citation(claim, *, stance: str | None = None) -> SkillCitation:
    """A SkillCitation that mirrors a real Claim (so the gate's quote-match + number checks pass)."""
    return SkillCitation(
        claim_id=claim.id,
        source_video_id=claim.source_video_id,
        timestamp_ms=claim.timestamp_ms,
        quote=claim.quote,
        technique=claim.technique,
        stance=stance if stance is not None else claim.stance,
    )


def make_section(
    claims: list,
    *,
    kind: SectionKind = SectionKind.CONSENSUS,
    body: str | None = None,
    stance: str | None = None,
) -> SkillSection:
    """Build a section from real claims (body defaults to their joined claim_text => self-grounded)."""
    first = claims[0]
    return SkillSection(
        kind=kind,
        topic=first.topic,
        technique=first.technique,
        stage=first.stage,
        genre=list(first.genre),
        stance=stance,
        body=body if body is not None else " ".join(c.claim_text for c in claims),
        citations=[make_citation(c, stance=stance) for c in claims],
        distinct_sources=len({c.source_video_id for c in claims}),
    )


def make_draft(
    default_claims: list,
    *,
    cell: ProductionCell | None = None,
    sections: list[SkillSection] | None = None,
    default_body: str | None = None,
    default_stance: str | None = None,
) -> SkillDraft:
    """Assemble a SkillDraft from real claims — the PASS baseline that gate tests then mutate to REJECT."""
    cell = cell or make_cell()
    default = make_section(default_claims, kind=SectionKind.DEFAULT, body=default_body, stance=default_stance)
    return SkillDraft(
        cell=cell,
        name=cell.slug,
        description="test skill",
        default=default,
        sections=sections if sections is not None else [],
        prompt_version="test/v1",
    )


@pytest.fixture
def mining_plane(claim_corpus):
    """A MiningPipeline wired over fakes: in-memory corpus of fixture snapshots + fake extractor + in-mem store.

    Returns ``(pipeline, store, targets)`` — drives the full extract -> verify -> dedup -> cross-reference
    -> persist flow with no API, no tokens, no DB.
    """
    corpus = InMemoryCorpusStore()
    clock = FakeClock()
    for vid, transcript in claim_corpus.transcripts.items():
        corpus.write_snapshot(transcript, snapshot_record(transcript, clock.now()))

    store = InMemoryClaimStore()
    extractor = FakeClaimExtractor(scripted=claim_corpus.scripted)
    pipeline = MiningPipeline(extractor, store, corpus, similarity=KeywordSimilarityIndex())
    targets = [
        MineTarget(video_id=vid, genres=claim_corpus.genres.get(vid, []))
        for vid in claim_corpus.video_ids
    ]
    return pipeline, store, targets
