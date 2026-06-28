"""Claim / ClaimCluster schema — the typed KNOW-05 boundary, incl. the no-synthesis field invariant."""

from __future__ import annotations

import pytest

from knowledge_pipeline.domain.claims import Claim, ClaimCluster
from knowledge_pipeline.domain.keys import compute_claim_id
from knowledge_pipeline.domain.models import CaptionSource

from .conftest import make_claim


def test_claim_id_is_deterministic_and_content_addressed():
    a = make_claim(video="v", ts_ms=8000, claim_text="High-pass the sub around 30 Hz.")
    b = make_claim(video="v", ts_ms=8000, claim_text="high-pass the sub around 30 hz")  # case/punct only
    # id is a pure content hash of (video, ts, normalized text, stance, technique) -> the two
    # normalize-equal claims (same stance/technique) share it.
    assert a.id == b.id == compute_claim_id(
        "v", 8000, "High-pass the sub around 30 Hz.", stance=a.stance, technique=a.technique
    )
    assert a.id.startswith("clm_")


def test_claim_id_changes_with_citation_anchor():
    base = make_claim(video="v", ts_ms=8000)
    assert base.id != make_claim(video="v", ts_ms=9000).id      # different timestamp
    assert base.id != make_claim(video="w", ts_ms=8000).id      # different source


def test_claim_topic_is_normalized_stage_slash_technique():
    c = make_claim(stage="Vocal Layering", technique="Vocal Stacking")
    assert c.topic == "vocal-layering/vocal-stacking"


def test_claim_is_frozen_and_typed():
    c = make_claim()
    assert isinstance(c.caption_source, CaptionSource)
    with pytest.raises(Exception):
        c.confidence = 0.1  # frozen


def test_claim_confidence_bounds_enforced():
    with pytest.raises(Exception):
        make_claim(confidence=1.5)


def test_no_synthesized_fields_on_claim():
    # The Phase-4 boundary, encoded structurally: every field is extracted-or-citation. No default,
    # recommendation, summary, or merged "best way" may exist on the schema.
    fields = set(Claim.model_fields.keys())
    assert fields == {
        "claim_text", "technique", "stage", "genre", "stance", "confidence",
        "source_video_id", "timestamp_ms", "quote", "caption_source",
    }
    forbidden = {"default", "recommendation", "recommended", "summary", "synthesis", "best", "verdict"}
    assert not (forbidden & {f.lower() for f in fields})


def test_cluster_consensus_counts_distinct_sources_not_repeats():
    # 3 claims from the SAME source + 1 from another -> 2 distinct sources, not 4.
    members = [
        make_claim(video="v1", ts_ms=1000, claim_text="a"),
        make_claim(video="v1", ts_ms=2000, claim_text="b"),
        make_claim(video="v1", ts_ms=3000, claim_text="c"),
        make_claim(video="v2", ts_ms=1000, claim_text="d"),
    ]
    cl = ClaimCluster(topic="bassline/sub-bass-highpass", stage="bassline",
                      technique="sub-bass-highpass", consensus=members)
    assert cl.distinct_consensus_sources == 2
    assert cl.is_contested is False
    assert cl.member_count == 4


def test_cluster_sides_group_conflicts_by_stance():
    flex = make_claim(video="vf", stance="flex-synth", technique="log-drum-sound-source", stage="drums")
    layered = make_claim(video="vl", stance="layered-samples", technique="log-drum-sound-source", stage="drums")
    cl = ClaimCluster(topic="drums/log-drum-sound-source", stage="drums",
                      technique="log-drum-sound-source", conflicts=[flex, layered])
    sides = cl.sides()
    assert set(sides.keys()) == {"flex-synth", "layered-samples"}
    assert cl.is_contested is True
    assert cl.distinct_conflict_sources == 2
