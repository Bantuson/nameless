"""SynthesisPipeline — the Phase-5 orchestration, pure over injected ports (KNOW-07/08/09).

Like the Phase-3/4 pipelines this contains NO ``anthropic``, NO sqlite, NO clock-of-its-own beyond an
injected ``now``. It wires the synthesis flow in the one correct order and turns the Phase-4 cited-claim
layer into authored, gated, draft Claude Skills:

    clusters = claim_store.list_clusters()                       [the Phase-4 evidence]
    claims   = {c.id: c for c in claim_store.list_claims()}      [the authoritative citation set]
    for cell in select_cells(clusters, p1_only):                 [KNOW-09: north-star cells first]
        draft  = synthesizer.synthesize(cell, clusters_for_cell) [KNOW-07: layered, only over claims]
        gate   = citation_gate(draft, claims, snapshots)         [KNOW-08: the HARD reject gate]
        if not gate.ok: record REJECTED (reasons); continue       [nothing untraceable ships]
        md     = emit_skill_md(draft, status=draft)               [KNOW-07: layered SKILL.md]
        store.upsert_skill(AuthoredSkill(..., status=draft))      [KNOW-11: draft until audited]

The defining design point: **the gate is not a port.** It is the same pure function for the real Claude
synthesizer and the fake template — you never want a "test gate" that is weaker than production. The model
(real or fake) gets no special pass; an untraceable draft is REJECTED identically either way. That is what
makes "quality in, quality out" a property of the system, not a hope about the model.

Every dependency is a port, so the whole flow runs in tests with a FakeSkillSynthesizer + an in-memory
skill store + the Phase-4 fakes — no API, no tokens, no DB.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from pydantic import BaseModel, Field

from .domain.skills import AuthoredSkill, SkillDraft, SkillStatus, compute_skill_id
from .ports import ClaimStore, CorpusStore, SkillStore, SkillSynthesizer
from .pure.cell_selection import clusters_for_cell, select_cells
from .pure.citation_gate import GateResult, citation_gate
from .pure.layered_emitter import emit_skill_md

logger = logging.getLogger("knowledge_pipeline.synthesis")


@dataclass
class SynthesisConfig:
    """Knobs for one synthesis run."""

    p1_only: bool = True               # author only the P1 north-star grid cells (FEATURES) by default
    gate_min_coverage: float = 0.6     # the ungrounded-assertion coverage floor for the gate


class SynthesisOutcome(BaseModel):
    """Compact per-cell result — safe to log/print (no SKILL.md body dump)."""

    cell: str
    status: str                        # authored | rejected
    skill_id: Optional[str] = None
    citation_count: int = 0
    distinct_sources: int = 0
    confidence: str = ""
    reasons: list[str] = Field(default_factory=list)


class SynthesisReport(BaseModel):
    """The roll-up of a synthesis run."""

    outcomes: list[SynthesisOutcome] = Field(default_factory=list)
    authored: int = 0
    rejected: int = 0
    total_cells: int = 0


def build_authored_skill(
    draft: SkillDraft,
    *,
    status: SkillStatus = SkillStatus.DRAFT,
    now: _dt.datetime,
) -> AuthoredSkill:
    """Assemble an :class:`AuthoredSkill` (incl. emitted body + audit roll-up) from a gated draft. Pure."""
    body_md = emit_skill_md(draft, status=status)
    consensus_topics = len({s.topic for s in draft.consensus_sections()})
    conflict_topics = len({s.topic for s in draft.conflict_sections()})
    citation_count = sum(len(s.citations) for s in draft.all_sections())
    return AuthoredSkill(
        id=compute_skill_id(draft.cell.stage, draft.cell.genre),
        name=draft.name,
        description=draft.description,
        stage=draft.cell.stage,
        genre=draft.cell.genre,
        status=status,
        relpath=draft.cell.relpath,
        prompt_version=draft.prompt_version,
        claim_ids=sorted(draft.cited_claim_ids),
        citation_count=citation_count,
        distinct_sources=draft.distinct_sources,
        default_source_count=draft.default.distinct_sources,
        default_contested=draft.default.stance is not None,
        consensus_topics=consensus_topics,
        conflict_topics=conflict_topics,
        body_sha256=hashlib.sha256(body_md.encode("utf-8")).hexdigest(),
        body_md=body_md,
        authored_at=now,
    )


class SynthesisPipeline:
    """Orchestrates the Phase-4 claim layer -> authored, gated, draft skills. Stateless; reusable."""

    def __init__(
        self,
        synthesizer: SkillSynthesizer,
        skill_store: SkillStore,
        claim_store: ClaimStore,
        *,
        corpus: Optional[CorpusStore] = None,
        config: Optional[SynthesisConfig] = None,
        now: Optional[Callable[[], _dt.datetime]] = None,
    ) -> None:
        self._synth = synthesizer
        self._store = skill_store
        self._claims = claim_store
        self._corpus = corpus
        self._config = config or SynthesisConfig()
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def _snapshots_for(self, draft: SkillDraft):
        """Load the snapshots for a draft's cited videos (for the gate's R5 rot check). ``None`` if no corpus."""
        if self._corpus is None:
            return None
        vids = {c.source_video_id for s in draft.all_sections() for c in s.citations}
        snaps = {}
        for vid in vids:
            snap = self._corpus.load_snapshot(vid)
            if snap is not None:
                snaps[vid] = snap
        return snaps

    def synthesize(self) -> SynthesisReport:
        """Select cells -> synthesize -> GATE -> emit draft skills. Idempotent (re-synthesis upserts by id)."""
        self._store.init_schema()
        cfg = self._config

        clusters = self._claims.list_clusters()
        claim_index = {c.id: c for c in self._claims.list_claims()}
        cells = select_cells(clusters, p1_only=cfg.p1_only)

        outcomes: list[SynthesisOutcome] = []
        authored = rejected = 0

        for cell in cells:
            cell_clusters = clusters_for_cell(clusters, cell)
            if not cell_clusters:
                continue  # defensive: select_cells only yields evidenced cells, but never synthesize empty
            draft = self._synth.synthesize(cell, cell_clusters)

            result: GateResult = citation_gate(
                draft, claim_index,
                snapshots=self._snapshots_for(draft),
                min_coverage=cfg.gate_min_coverage,
            )
            if not result.ok:
                rejected += 1
                outcomes.append(
                    SynthesisOutcome(cell=cell.slug, status="rejected", reasons=result.reasons)
                )
                logger.warning("REJECTED %s: %s", cell.slug, "; ".join(result.reasons))
                continue

            skill = build_authored_skill(draft, status=SkillStatus.DRAFT, now=self._now())
            self._store.upsert_skill(skill)
            authored += 1
            outcomes.append(
                SynthesisOutcome(
                    cell=cell.slug,
                    status="authored",
                    skill_id=skill.id,
                    citation_count=skill.citation_count,
                    distinct_sources=skill.distinct_sources,
                    confidence=skill.confidence_tier,
                )
            )

        report = SynthesisReport(
            outcomes=outcomes, authored=authored, rejected=rejected, total_cells=len(cells)
        )
        logger.info("synthesis: %d authored, %d rejected (of %d cells)", authored, rejected, len(cells))
        return report
