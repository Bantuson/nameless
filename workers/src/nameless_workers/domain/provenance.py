"""Fragment provenance — a faithful mirror of ``nameless_core::provenance::Provenance``.

Provenance drives WHICH lifecycle path a fragment travels (PRD §6). ``human_recorded``, ``derived``,
and ``sampled`` travel the *human* path (capture → analyze → place …); ``ai_generated`` must clear the
eval gate. The Phase-2 feature worker only ever analyzes human-path fragments, but the full 4-variant
set + the ``travels_human_path`` / ``is_ai`` predicates are mirrored here so the transition mirror in
:mod:`nameless_workers.domain.state` can reproduce the Rust guards exactly.

The string labels are the canonical snake_case DB-enum labels (``provenance`` type in
``migrations/0001_init.sql``); they MUST match the Rust ``as_str``/``from_db_str`` byte-for-byte.
"""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    """Where a fragment's audio originated. Values are the canonical DB-enum labels."""

    HUMAN_RECORDED = "human_recorded"
    AI_GENERATED = "ai_generated"
    DERIVED = "derived"
    SAMPLED = "sampled"

    @property
    def travels_human_path(self) -> bool:
        """True for provenances that travel the human lifecycle (no eval gate).

        ``human_recorded``, ``derived`` and ``sampled`` are all real source audio — there is nothing
        to score generated-vs-source fidelity against — so they never pass the AI eval gate. Mirror of
        ``Provenance::travels_human_path``.
        """
        return self in (
            Provenance.HUMAN_RECORDED,
            Provenance.DERIVED,
            Provenance.SAMPLED,
        )

    @property
    def is_ai(self) -> bool:
        """True only for ``ai_generated`` — the provenance that must clear the eval gate."""
        return self is Provenance.AI_GENERATED

    @classmethod
    def from_db_str(cls, s: str) -> "Provenance":
        """Parse a canonical DB label. Raises ``ValueError`` on an unknown label (no silent default)."""
        return cls(s)
