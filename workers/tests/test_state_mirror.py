"""The cross-language state-machine mirror — proves the Python ``transition`` matches the Rust spec.

This reproduces the Rust ``test_full_transition_matrix`` (crates/nameless-core/src/state_machine.rs):
an independently-written allow-list of EVERY legal edge, checked against ``transition`` over the full
4 × 12 × 10 = 480 cartesian product. If the Python mirror and the Rust rules ever drift, this fails.
"""

from __future__ import annotations

import pytest

from nameless_workers.domain.provenance import Provenance
from nameless_workers.domain.state import (
    FragmentState as S,
    IllegalTransition,
    Transition as T,
    apply_guarded,
    transition,
)

ALL_PROVENANCE = list(Provenance)
ALL_STATES = list(S)
ALL_TRANSITIONS = list(T)


def legal_edges() -> list[tuple[Provenance, S, T, S]]:
    """The hand-written allow-list of every legal edge — the executable spec (mirrors Rust)."""
    edges: list[tuple[Provenance, S, T, S]] = []

    # Shared post-placement tail is legal for ALL provenances (unguarded in `transition`).
    for p in ALL_PROVENANCE:
        edges.append((p, S.PLACED, T.MIX, S.MIXED))
        edges.append((p, S.MIXED, T.RENDER, S.RENDERED))

    # Human / sampled / derived analysis + placement path.
    for p in (Provenance.HUMAN_RECORDED, Provenance.SAMPLED, Provenance.DERIVED):
        edges.append((p, S.CAPTURED, T.ANALYZE, S.ANALYZING))
        edges.append((p, S.ANALYZING, T.MARK_ANALYZED, S.ANALYZED))
        edges.append((p, S.ANALYZED, T.PLACE, S.PLACED))

    # AI generation + eval-gate path.
    ai = Provenance.AI_GENERATED
    edges.append((ai, S.REQUESTED, T.GENERATE, S.GENERATING))
    edges.append((ai, S.GENERATING, T.MARK_GENERATED, S.GENERATED))
    edges.append((ai, S.GENERATED, T.EVALUATE, S.EVALUATING))
    edges.append((ai, S.EVALUATING, T.PROMOTE, S.PROMOTED))
    edges.append((ai, S.EVALUATING, T.REJECT, S.REJECTED))
    edges.append((ai, S.PROMOTED, T.PLACE, S.PLACED))
    return edges


def test_full_transition_matrix():
    legal = {(p, f, t): nxt for (p, f, t, nxt) in legal_edges()}
    for p in ALL_PROVENANCE:
        for frm in ALL_STATES:
            for t in ALL_TRANSITIONS:
                expected = legal.get((p, frm, t))
                if expected is not None:
                    assert transition(p, frm, t) is expected, (p, frm, t)
                else:
                    with pytest.raises(IllegalTransition):
                        transition(p, frm, t)


def test_cannot_place_unanalyzed():
    # The headline CAP-05 invariant the Phase-2 worker must respect.
    for p in (Provenance.HUMAN_RECORDED, Provenance.SAMPLED, Provenance.DERIVED):
        with pytest.raises(IllegalTransition):
            transition(p, S.CAPTURED, T.PLACE)
        with pytest.raises(IllegalTransition):
            transition(p, S.ANALYZING, T.PLACE)
        assert transition(p, S.ANALYZED, T.PLACE) is S.PLACED


def test_worker_drives_only_the_analysis_edges():
    # Exactly the two transitions the consumer issues, on the human path.
    assert transition(Provenance.HUMAN_RECORDED, S.CAPTURED, T.ANALYZE) is S.ANALYZING
    assert transition(Provenance.HUMAN_RECORDED, S.ANALYZING, T.MARK_ANALYZED) is S.ANALYZED


def test_ai_fragment_cannot_be_analyzed():
    # A FeatureExtract job should never target ai_generated material; the guard refuses it structurally.
    with pytest.raises(IllegalTransition):
        transition(Provenance.AI_GENERATED, S.CAPTURED, T.ANALYZE)


def test_sampled_travels_human_path():
    assert transition(Provenance.SAMPLED, S.CAPTURED, T.ANALYZE) is S.ANALYZING
    assert transition(Provenance.SAMPLED, S.ANALYZED, T.PLACE) is S.PLACED
    with pytest.raises(IllegalTransition):
        transition(Provenance.SAMPLED, S.REQUESTED, T.GENERATE)


def test_rejected_is_terminal():
    for p in ALL_PROVENANCE:
        for t in ALL_TRANSITIONS:
            with pytest.raises(IllegalTransition):
                transition(p, S.REJECTED, t)


def test_illegal_transition_names_the_offending_pair():
    err = None
    try:
        transition(Provenance.HUMAN_RECORDED, S.CAPTURED, T.PLACE)
    except IllegalTransition as e:
        err = e
    assert err is not None
    assert err.from_state is S.CAPTURED
    assert err.transition is T.PLACE
    assert "place" in str(err) and "captured" in str(err)


def test_apply_guarded_refuses_sampled_place_but_mirrors_transition_otherwise():
    """CR-01: ``apply_guarded`` is the *mutation*-layer mirror of Rust ``Fragment::apply``.

    It refuses ``(Sampled, PLACE)`` outright — even from ``ANALYZED`` where bare ``transition`` legally
    yields ``PLACED`` — so the only door to placing a sample is an attribution-checked path (SAMP-03).
    For every non-sampled provenance, and for every non-PLACE verb, it is transparent: identical to
    bare ``transition`` (legal edges pass through, illegal edges raise)."""
    # The sampled-placement refusal: bare transition allows it, the mutation guard does not.
    assert transition(Provenance.SAMPLED, S.ANALYZED, T.PLACE) is S.PLACED
    with pytest.raises(IllegalTransition):
        apply_guarded(Provenance.SAMPLED, S.ANALYZED, T.PLACE)

    # Non-PLACE verbs on a sample are unaffected (analysis path still flows).
    assert apply_guarded(Provenance.SAMPLED, S.CAPTURED, T.ANALYZE) is S.ANALYZING
    assert apply_guarded(Provenance.SAMPLED, S.ANALYZING, T.MARK_ANALYZED) is S.ANALYZED

    # Non-sampled placement is unaffected — apply_guarded == transition for every other triple.
    for p in ALL_PROVENANCE:
        for frm in ALL_STATES:
            for t in ALL_TRANSITIONS:
                if p is Provenance.SAMPLED and t is T.PLACE:
                    with pytest.raises(IllegalTransition):
                        apply_guarded(p, frm, t)
                    continue
                try:
                    expected = transition(p, frm, t)
                except IllegalTransition:
                    with pytest.raises(IllegalTransition):
                        apply_guarded(p, frm, t)
                else:
                    assert apply_guarded(p, frm, t) is expected, (p, frm, t)


def test_labels_match_the_db_enum_strings():
    # The Python enum values must equal the canonical snake_case DB/Rust labels exactly.
    assert [s.value for s in S][:6] == [
        "captured",
        "analyzing",
        "analyzed",
        "placed",
        "mixed",
        "rendered",
    ]
    assert {p.value for p in Provenance} == {
        "human_recorded",
        "ai_generated",
        "derived",
        "sampled",
    }
