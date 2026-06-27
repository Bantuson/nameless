"""ClaimStore contract — the in-memory fake AND the real sqlite store satisfy the SAME behavior.

sqlite3 is stdlib, so the REAL store runs on the base env: this verifies the actual persistence path
(claims + clusters + members round-trip, conflict sides survive, idempotent upsert), not just a double.
"""

from __future__ import annotations

import pytest

from knowledge_pipeline.adapters import InMemoryClaimStore, SqliteClaimStore
from knowledge_pipeline.pure.cross_reference import cross_reference

from .conftest import make_claim


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        s = InMemoryClaimStore()
    else:
        s = SqliteClaimStore(tmp_path / "registry.sqlite")
    s.init_schema()
    return s


def _claims():
    return [
        # consensus topic, 2 distinct sources
        make_claim(video="v1", genre=["deep-house"], ts_ms=8000, claim_text="hp sub a"),
        make_claim(video="v2", genre=["rnb"], ts_ms=5000, claim_text="hp sub b"),
        # contested topic, both stances
        make_claim(video="vf", genre=["amapiano"], technique="log-drum-source", stage="drums",
                   stance="flex-synth", claim_text="build on flex"),
        make_claim(video="vl", genre=["amapiano"], technique="log-drum-source", stage="drums",
                   stance="layered-samples", claim_text="layer samples"),
    ]


def test_claim_upsert_get_and_list_filters(store):
    claims = _claims()
    store.upsert_claims(claims, verified={c.id: True for c in claims})

    one = claims[0]
    got = store.get_claim(one.id)
    assert got is not None and got.id == one.id and got.quote == one.quote

    assert {c.id for c in store.list_claims(stage="drums")} == {claims[2].id, claims[3].id}
    assert {c.id for c in store.list_claims(genre="rnb")} == {claims[1].id}
    assert {c.id for c in store.list_claims(source_video_id="v1")} == {claims[0].id}
    assert store.list_claims(min_confidence=0.95) == []


def test_upsert_is_idempotent_on_id(store):
    claims = _claims()
    store.upsert_claims(claims)
    store.upsert_claims(claims)  # re-mine
    assert store.stats().total_claims == len(claims)


def test_clusters_roundtrip_preserves_both_conflict_sides(store):
    claims = _claims()
    store.upsert_claims(claims, verified={c.id: True for c in claims})
    clusters = cross_reference(store.list_claims())
    store.replace_clusters(clusters)

    contested = store.list_clusters(contested_only=True)
    assert len(contested) == 1
    cl = store.get_cluster("drums/log-drum-source")
    assert cl is not None
    assert cl.is_contested is True
    assert len(cl.conflicts) == 2 and cl.consensus == []
    assert set(cl.sides().keys()) == {"flex-synth", "layered-samples"}

    consensus = store.get_cluster("bassline/sub-bass-highpass")
    assert consensus is not None
    assert len(consensus.consensus) == 2
    assert consensus.distinct_consensus_sources == 2


def test_replace_clusters_is_wholesale(store):
    store.upsert_claims(_claims())
    store.replace_clusters(cross_reference(store.list_claims()))
    n1 = len(store.list_clusters())
    # replace with an empty set -> all clusters gone (clusters are a global function of claims)
    store.replace_clusters([])
    assert store.list_clusters() == []
    assert n1 >= 2


def test_stats_rollup(store):
    claims = _claims()
    store.upsert_claims(claims, verified={c.id: True for c in claims})
    store.replace_clusters(cross_reference(store.list_claims()))
    stats = store.stats()
    assert stats.total_claims == 4
    assert stats.contested_clusters == 1
    assert stats.citation_verified == 4
    assert stats.by_stage.get("drums") == 2
