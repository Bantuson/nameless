"""MiningPipeline end-to-end over the claim fixtures — extract -> verify -> dedup -> cross-ref -> persist.

All on fakes (FakeClaimExtractor + InMemoryClaimStore + in-memory corpus): no API, no tokens, no DB.
Exercises the real control flow + the KNOW-05/06 guarantees over the bundled consensus set and the
amapiano FLEX-vs-layered conflict.
"""

from __future__ import annotations

from knowledge_pipeline.adapters import FakeClaimExtractor, FakeClock, InMemoryClaimStore, InMemoryCorpusStore
from knowledge_pipeline.domain.models import CaptionSource, RawTranscript, TranscriptSegment
from knowledge_pipeline.mining_pipeline import MineTarget, MiningConfig, MiningPipeline
from knowledge_pipeline.pure.snapshot import snapshot_record


def test_full_mine_produces_cited_claims_and_clusters(mining_plane):
    pipeline, store, targets = mining_plane
    report = pipeline.mine(targets)

    # 7 fixture claims: deephouse(2) + rnb(2) + amapiano_subbass(1) + flex(1) + layered(1)
    assert report.total_claims == 7
    assert report.duplicates_dropped == 0
    # every scripted quote is verbatim transcript text -> all citations verify
    assert sum(o.citations_ok for o in report.outcomes) == 7
    assert sum(o.citations_failed for o in report.outcomes) == 0

    # clusters: sub-bass-highpass (consensus, 3 src), sub-bass-mono (1), vocal-stacking (1), log-drum (contested)
    assert report.total_clusters == 4
    assert report.contested_clusters == 1


def test_consensus_counts_three_distinct_sources(mining_plane):
    pipeline, store, targets = mining_plane
    pipeline.mine(targets)
    cl = store.get_cluster("bassline/sub-bass-highpass")
    assert cl is not None
    assert cl.is_contested is False
    assert cl.distinct_consensus_sources == 3       # deep-house + rnb + amapiano, one claim each


def test_conflict_preserved_both_sides(mining_plane):
    pipeline, store, targets = mining_plane
    pipeline.mine(targets)
    cl = store.get_cluster("drums/log-drum-sound-source")
    assert cl is not None
    assert cl.is_contested is True
    assert cl.consensus == []                        # no opinionated default in Phase 4
    assert len(cl.conflicts) == 2
    assert set(cl.sides().keys()) == {"flex-synth", "layered-samples"}


def test_re_mine_is_idempotent(mining_plane):
    pipeline, store, targets = mining_plane
    first = pipeline.mine(targets)
    second = pipeline.mine(targets)
    assert second.total_claims == first.total_claims == 7   # content-addressed upsert, no duplication
    assert second.total_clusters == first.total_clusters


def test_each_stored_claim_is_marked_citation_verified(mining_plane):
    pipeline, store, targets = mining_plane
    pipeline.mine(targets)
    assert store.stats().citation_verified == store.stats().total_claims


def test_require_citation_is_on_by_default():
    # WR-05: the safe path must be the default — a claim whose quote is absent from the transcript
    # (the real LLM's failure mode) is rejected, not persisted with an invented timestamp.
    assert MiningConfig().require_citation is True


def test_default_pipeline_drops_a_hallucinated_claim():
    # The default MiningPipeline (no explicit config) drops the uncited claim.
    corpus = InMemoryCorpusStore()
    transcript = RawTranscript(
        video_id="v",
        caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=4.0, duration_s=5.0, text="High-pass the pads at 250 hz.")],
    )
    corpus.write_snapshot(transcript, snapshot_record(transcript, FakeClock().now()))

    from .conftest import make_claim

    good = make_claim(video="v", ts_ms=4000, technique="high-pass", stage="mixing",
                      quote="High-pass the pads at 250 hz.", claim_text="High-pass the pads at 250 Hz.")
    bad = make_claim(video="v", ts_ms=4000, technique="reverb", stage="atmosphere",
                     quote="add a tasteful purple gradient", claim_text="add a purple gradient")
    store = InMemoryClaimStore()
    pipeline = MiningPipeline(FakeClaimExtractor(scripted={"v": [good, bad]}), store, corpus)
    report = pipeline.mine([MineTarget(video_id="v")])
    assert report.total_claims == 1                  # default enforces citation
    assert store.get_claim(bad.id) is None


def test_require_citation_drops_a_hallucinated_claim():
    # A scripted claim whose quote is NOT in the transcript -> citation fails -> dropped when required.
    corpus = InMemoryCorpusStore()
    transcript = RawTranscript(
        video_id="v",
        caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=4.0, duration_s=5.0, text="High-pass the pads at 250 hz.")],
    )
    corpus.write_snapshot(transcript, snapshot_record(transcript, FakeClock().now()))

    from .conftest import make_claim

    good = make_claim(video="v", ts_ms=4000, technique="high-pass", stage="mixing",
                      quote="High-pass the pads at 250 hz.", claim_text="High-pass the pads at 250 Hz.")
    bad = make_claim(video="v", ts_ms=4000, technique="reverb", stage="atmosphere",
                     quote="add a tasteful purple gradient", claim_text="add a purple gradient")
    extractor = FakeClaimExtractor(scripted={"v": [good, bad]})

    store = InMemoryClaimStore()
    pipeline = MiningPipeline(extractor, store, corpus, config=MiningConfig(require_citation=True))
    report = pipeline.mine([MineTarget(video_id="v")])

    assert report.total_claims == 1                  # the hallucinated claim was dropped
    assert store.get_claim(good.id) is not None
    assert store.get_claim(bad.id) is None
