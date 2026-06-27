"""FakeSkillSynthesizer — the deterministic :class:`~knowledge_pipeline.ports.SkillSynthesizer` for tests.

Stands in for Claude with ZERO API. It delegates to the PURE
:func:`~knowledge_pipeline.pure.synthesis_template.template_synthesize`, so the layered draft it produces
is composed verbatim from the cell's claim text — structurally incapable of introducing a claim, number,
or technique not in the input clusters. That is the synthesis-only-over-claims invariant, made checkable:
the contract test runs this fake over the fixtures, extracts every number/citation from the draft, and
asserts each one is present in the input clusters.

Optional ``scripted`` overrides (by ``cell.slug``) let a test pin an exact draft; absent a script it falls
back to the deterministic template — the reference behaviour the gate + emitter run against offline.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from ..domain.claims import ClaimCluster
from ..domain.skills import ProductionCell, SkillDraft
from ..pure.synthesis_template import template_synthesize


class FakeSkillSynthesizer:
    """Deterministic, LLM-free skill synthesizer over the pure template (+ optional scripted overrides)."""

    def __init__(self, scripted: Optional[Mapping[str, SkillDraft]] = None) -> None:
        self._scripted = dict(scripted or {})
        self.calls: list[str] = []  # which cells were synthesized (test assertions)

    def synthesize(self, cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> SkillDraft:
        self.calls.append(cell.slug)
        preset = self._scripted.get(cell.slug)
        if preset is not None:
            return preset
        return template_synthesize(cell, clusters)
