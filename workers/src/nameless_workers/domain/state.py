"""The fragment lifecycle — a deliberate, minimal mirror of the canonical Rust state machine.

CANONICAL AUTHORITY: ``crates/nameless-core/src/state_machine.rs``. Rust enforces every transition
with one exhaustive ``match`` and is the single source of truth on transition legality (PRD §7). This
module re-encodes the SAME rules in Python because the Phase-2 worker, after computing features, must
advance ``Captured → Analyzing → Analyzed`` itself — and it must NOT be able to drive an illegal edge.

WHY MIRROR INSTEAD OF CALL ACROSS THE SEAM: the worker plane is a separate process in a separate
language. Making a network/IPC round-trip to Rust just to validate a state edge would couple the
worker to the control plane's availability for a rule that is a tiny pure function. Instead we mirror
the pure function and pin the two together with an *exhaustive* matrix test (see
``tests/test_state_mirror.py``) that reproduces the Rust 480-triple matrix. If the Rust rules ever
change, that test is where the drift is caught. This is the cross-language state-seam design tension,
surfaced on purpose (and discussed in the phase SUMMARY).

The worker only ever issues ``ANALYZE`` and ``MARK_ANALYZED``; the rest of the table exists so the
mirror is provably faithful, not so the worker uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .provenance import Provenance


class FragmentState(str, Enum):
    """Every lifecycle state (PRD §7). Values are the canonical ``fragment_state`` DB-enum labels."""

    # ---- human / sampled / derived path ----
    CAPTURED = "captured"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    PLACED = "placed"
    MIXED = "mixed"
    RENDERED = "rendered"
    # ---- ai generation + eval-gate path ----
    REQUESTED = "requested"
    GENERATING = "generating"
    GENERATED = "generated"
    EVALUATING = "evaluating"
    PROMOTED = "promoted"
    REJECTED = "rejected"

    @classmethod
    def from_db_str(cls, s: str) -> "FragmentState":
        """Parse a canonical DB label; raises ``ValueError`` on an unknown label."""
        return cls(s)


class Transition(str, Enum):
    """Every transition verb that can be *attempted* (mirror of Rust ``Transition``)."""

    # human path
    ANALYZE = "analyze"
    MARK_ANALYZED = "mark_analyzed"
    # ai path
    GENERATE = "generate"
    MARK_GENERATED = "mark_generated"
    EVALUATE = "evaluate"
    PROMOTE = "promote"
    REJECT = "reject"
    # shared tail
    PLACE = "place"
    MIX = "mix"
    RENDER = "render"


@dataclass(frozen=True)
class IllegalTransition(Exception):
    """A rejected transition attempt, carrying the offending pair so the failure names itself.

    Raised (never silently swallowed) so callers MUST handle the illegal case — there is no no-op
    path that could let an invalid move slip through. Mirror of Rust ``IllegalTransition``.
    """

    from_state: FragmentState
    transition: Transition

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        return (
            f"illegal transition: cannot apply {self.transition.value} "
            f"from state {self.from_state.value}"
        )


def transition(
    provenance: Provenance,
    from_state: FragmentState,
    t: Transition,
) -> FragmentState:
    """The single checked transition function. Pure: output depends only on the inputs.

    A faithful mirror of ``nameless_core::state_machine::transition``. Every legal edge returns the
    next state; everything else raises :class:`IllegalTransition` (the only "wildcard" arm — it never
    returns a state, so a new legal edge must be added explicitly here AND in Rust).

    Structural guarantees preserved from Rust:
      * ``PLACE`` is reachable only from ``ANALYZED`` (human/sampled/derived) or ``PROMOTED`` (ai)
        ⇒ an unanalyzed/ungated fragment can never be placed.
      * there is no ``GENERATED → PLACED`` edge ⇒ the eval gate is the only path for AI material.
      * ``REJECTED`` is terminal.
    """
    S, T = FragmentState, Transition
    pair = (from_state, t)

    # ---- human / sampled / derived analysis path (guarded by travels_human_path) ----
    if pair == (S.CAPTURED, T.ANALYZE) and provenance.travels_human_path:
        return S.ANALYZING
    if pair == (S.ANALYZING, T.MARK_ANALYZED) and provenance.travels_human_path:
        return S.ANALYZED
    if pair == (S.ANALYZED, T.PLACE) and provenance.travels_human_path:
        return S.PLACED

    # ---- ai generation + eval-gate path (guarded by is_ai) ----
    if pair == (S.REQUESTED, T.GENERATE) and provenance.is_ai:
        return S.GENERATING
    if pair == (S.GENERATING, T.MARK_GENERATED) and provenance.is_ai:
        return S.GENERATED
    if pair == (S.GENERATED, T.EVALUATE) and provenance.is_ai:
        return S.EVALUATING
    if pair == (S.EVALUATING, T.PROMOTE) and provenance.is_ai:
        return S.PROMOTED
    if pair == (S.EVALUATING, T.REJECT) and provenance.is_ai:
        return S.REJECTED
    if pair == (S.PROMOTED, T.PLACE) and provenance.is_ai:
        return S.PLACED

    # ---- shared post-placement tail (legal for ALL provenances, unguarded — matches Rust) ----
    if pair == (S.PLACED, T.MIX):
        return S.MIXED
    if pair == (S.MIXED, T.RENDER):
        return S.RENDERED

    # ---- everything else is illegal; this arm NEVER returns a state ----
    raise IllegalTransition(from_state=from_state, transition=t)


def apply_guarded(
    provenance: Provenance,
    from_state: FragmentState,
    t: Transition,
) -> FragmentState:
    """The *mutation* chokepoint — mirrors Rust ``Fragment::apply`` (state_machine.rs / fragment.rs).

    Where :func:`transition` is the bare lifecycle matrix (and faithfully still allows
    ``(Sampled, ANALYZED, PLACE) → PLACED`` at the *lifecycle* level), this guard adds the extra
    precondition Rust's ``apply`` enforces ON TOP of it: **``apply`` refuses ``(Sampled, PLACE)``
    outright** (`fragment.rs`), because placing a sample carries an attribution requirement that a
    bare advance cannot supply. The ONLY sanctioned door to place a sample is an attribution-checked
    ``place(Some(&CompleteAttribution))`` (SAMP-03 — "there is no ungated path that writes ``Placed``
    onto a sample").

    Every repo ``advance()`` routes through THIS function, not bare :func:`transition`, so the Python
    worker plane cannot drive a ``sampled`` fragment to ``placed`` without going through an
    attribution-aware path — keeping the Python mutation layer byte-consistent with the stricter Rust
    mutation layer (closing the CR-01 cross-language gate divergence). For human / ai / derived
    material the guard is transparent: it falls straight through to :func:`transition`.
    """
    if provenance is Provenance.SAMPLED and t is Transition.PLACE:
        # SAMP-03: a sample reaches Placed only via an attribution-checked place(), never bare advance.
        raise IllegalTransition(from_state=from_state, transition=t)
    return transition(provenance, from_state, t)
