"""cross_reference — consensus XOR preserved conflict (KNOW-06). The no-synthesis invariant lives here."""

from __future__ import annotations

from knowledge_pipeline.pure.cross_reference import cross_reference

from .conftest import make_claim


def _consensus_set():
    # same topic (bassline/sub-bass-highpass), 3 DISTINCT sources -> genuine cross-source consensus.
    return [
        make_claim(video="deephouse", genre=["deep-house"], ts_ms=8000, claim_text="hp sub 30hz a"),
        make_claim(video="rnb", genre=["rnb"], ts_ms=5000, claim_text="hp sub 30hz b"),
        make_claim(video="amapiano", genre=["amapiano"], ts_ms=12000, claim_text="hp sub 30hz c"),
    ]


def _conflict_pair():
    # same topic (drums/log-drum-source), two opposing stances -> contested, both preserved.
    return [
        make_claim(video="flexvid", genre=["amapiano"], technique="log-drum-source", stage="drums",
                   stance="flex-synth", claim_text="build on FLEX"),
        make_claim(video="layervid", genre=["amapiano"], technique="log-drum-source", stage="drums",
                   stance="layered-samples", claim_text="layer samples"),
    ]


def test_uncontested_topic_becomes_consensus_with_distinct_source_count():
    clusters = cross_reference(_consensus_set())
    assert len(clusters) == 1
    cl = clusters[0]
    assert cl.topic == "bassline/sub-bass-highpass"
    assert cl.is_contested is False
    assert len(cl.consensus) == 3 and cl.conflicts == []
    assert cl.distinct_consensus_sources == 3
    assert sorted(cl.genre) == ["amapiano", "deep-house", "rnb"]  # cross-genre union preserved


def test_contested_topic_preserves_both_sides_and_picks_no_winner():
    clusters = cross_reference(_conflict_pair())
    assert len(clusters) == 1
    cl = clusters[0]
    assert cl.is_contested is True
    assert cl.consensus == []                 # Phase 4 does NOT promote a default
    assert len(cl.conflicts) == 2             # both camps survive
    assert set(cl.sides().keys()) == {"flex-synth", "layered-samples"}
    assert {c.source_video_id for c in cl.conflicts} == {"flexvid", "layervid"}


def test_conflict_is_never_collapsed_into_one_claim():
    # The single most important invariant: a disagreement is data, never averaged/deleted.
    clusters = cross_reference(_conflict_pair())
    cl = clusters[0]
    # both distinct claim ids present; nothing merged.
    assert len({c.id for c in cl.conflicts}) == 2


def test_no_claim_is_dropped_anywhere():
    claims = _consensus_set() + _conflict_pair()
    clusters = cross_reference(claims)
    placed = sum(len(cl.consensus) + len(cl.conflicts) for cl in clusters)
    assert placed == len(claims)              # extraction-only: every input atom survives


def test_same_source_repeats_do_not_inflate_corroboration():
    # 4 claims, but only 3 distinct sources (deephouse appears twice) -> corroboration is 3, not 4.
    claims = _consensus_set() + [
        make_claim(video="deephouse", genre=["deep-house"], ts_ms=20000, claim_text="hp sub 30hz again")
    ]
    cl = cross_reference(claims)[0]
    assert len(cl.consensus) == 4
    assert cl.distinct_consensus_sources == 3


def test_neutral_claim_does_not_make_a_topic_contested():
    # one advocated stance + one neutral fact on the same technique is agreement, not a conflict.
    claims = [
        make_claim(video="a", technique="log-drum-source", stage="drums", stance="flex-synth"),
        make_claim(video="b", technique="log-drum-source", stage="drums", stance=None,
                   claim_text="shape the log drum with a soft clipper"),
    ]
    cl = cross_reference(claims)[0]
    assert cl.is_contested is False
    assert len(cl.consensus) == 2
