"""Typed skill-synthesis domain (pydantic v2) — the Phase-5 boundary (KNOW-07/08/09/11).

Phase 4 produced cited :class:`~knowledge_pipeline.domain.claims.Claim` atoms grouped into preserved
``ClaimCluster`` consensus/conflict. Phase 5 is the ONLY place a decision is made *on top of* that
evidence: it authors **layered Claude Skills** — an opinionated default the agent acts on, PLUS the
preserved consensus + contested evidence with per-claim citations. These types are the typed shape of
that boundary, and the discipline is encoded in their structure:

  * :class:`ProductionCell` — one ``(stage, genre)`` leaf of the production-stack-of-skill grid. One cell
    -> one authored ``skills/production/<stage>/<genre>/SKILL.md``.
  * :class:`SkillCitation` — a *receipt*: the claim id + its verbatim source quote + ``video_id @ ts``.
    A skill section may assert nothing that is not backed by one of these — and the citation re-states the
    claim's real ``quote`` so the hard gate (KNOW-08) can confirm it was not fabricated.
  * :class:`SkillSection` — one block of synthesized prose (``kind`` = default | consensus | conflict)
    whose ``body`` is composed ONLY from cited claim text. The gate checks each section's numbers against
    *its own* citations, so an invented parameter in one block cannot hide behind another block's evidence.
  * :class:`SkillDraft` — the synthesizer's pre-gate, pre-emit output: the cell, the opinionated
    ``default`` section, and the ``sections`` (consensus + both camps of every conflict). It carries NO
    rendered markdown and NO status — emission + status are downstream of the gate.
  * :class:`AuthoredSkill` — a draft that PASSED the gate and was emitted: the SKILL.md text, its
    ``status`` (``draft`` until a human spot-audit promotes it — KNOW-11), and the audit-facing roll-up
    (distinct sources, default corroboration, contested-default flag) the ``skills audit`` flow reads.

The grid data (which cells are P1, and the north-star authoring order) lives here as reviewable data
next to the types, mirroring :mod:`knowledge_pipeline.domain.genres`; the *ordering logic* is the pure
:mod:`knowledge_pipeline.pure.cell_selection`.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .keys import normalize_key


# ============================================================================================
# Enums
# ============================================================================================


class SkillStatus(str, Enum):
    """A skill's lifecycle state. ``draft`` until a human spot-audit promotes it (KNOW-11).

    Nothing ships to the M1 arranger/mixer agents unaudited: synthesis emits ``draft``; ``skills audit``
    surfaces a sampled set with citation coverage + flags; ``skills promote`` (a deliberate human action)
    is the only transition to ``promoted``.
    """

    DRAFT = "draft"
    PROMOTED = "promoted"


class SectionKind(str, Enum):
    """The layer a skill section belongs to (KNOW-07 — opinionated default + preserved evidence)."""

    DEFAULT = "default"        # the opinionated decision the agent acts on (one per skill, cell-level)
    CONSENSUS = "consensus"    # an uncontested topic: corroborated claims across distinct sources
    CONFLICT = "conflict"      # ONE camp of a contested topic — both camps emitted, never collapsed


# ============================================================================================
# Cell — a (stage, genre) leaf of the production-stack-of-skill grid
# ============================================================================================


class ProductionCell(BaseModel):
    """One ``(stage, genre)`` leaf — the unit a single authored SKILL.md covers (KNOW-09)."""

    model_config = ConfigDict(frozen=True)

    stage: str
    genre: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def slug(self) -> str:
        """Kebab id used as the Claude-skill ``name`` and the on-disk dir, e.g. ``amapiano-drums``."""
        return f"{normalize_key(self.genre)}-{normalize_key(self.stage)}"

    @property
    def relpath(self) -> str:
        """The authored skill's path under the production tree (POSIX, stable across OS)."""
        return f"skills/production/{normalize_key(self.stage)}/{normalize_key(self.genre)}/SKILL.md"


# ============================================================================================
# Citation + section + draft
# ============================================================================================


class SkillCitation(BaseModel):
    """A receipt for one asserted point: the claim id + the verbatim source quote + ``video_id @ ts``.

    The ``quote`` is re-stated from the cited claim (not authored anew) so the gate can confirm a section
    asserts nothing the source did not say. ``stance`` rides along for conflict camps.
    """

    model_config = ConfigDict(frozen=True)

    claim_id: str
    source_video_id: str
    timestamp_ms: int = Field(ge=0)
    quote: str
    technique: str = ""
    stance: Optional[str] = None


class SkillSection(BaseModel):
    """One synthesized block — its ``body`` composed ONLY from cited claim text (KNOW-07/08).

    INVARIANT (the synthesis-only boundary): every number and assertion in ``body`` must trace to one of
    this section's own ``citations``. The gate enforces it per-section, so corroboration and conflict each
    stand on their own evidence. ``distinct_sources`` is the corroboration signal the emitter surfaces.
    """

    model_config = ConfigDict(frozen=True)

    kind: SectionKind
    topic: str                              # "<stage>/<technique>" — the cross-reference key
    technique: str
    stage: str
    genre: list[str] = Field(default_factory=list)
    stance: Optional[str] = None            # set for CONFLICT camps (e.g. "flex-synth")
    body: str                               # asserted prose, built verbatim from claim_text(s)
    citations: list[SkillCitation] = Field(default_factory=list)
    distinct_sources: int = 0

    @property
    def cited_ids(self) -> set[str]:
        return {c.claim_id for c in self.citations}


class SkillDraft(BaseModel):
    """The synthesizer's output BEFORE the gate + emission — pure layered content over the claim set.

    ``default`` is the cell-level opinionated guidance the agent acts on; ``sections`` are the per-topic
    consensus blocks and the (one-per-camp) conflict blocks. There is no markdown and no status here —
    those are decided downstream, only after :func:`~knowledge_pipeline.pure.citation_gate.citation_gate`
    passes. :meth:`all_sections` is what the gate iterates.
    """

    model_config = ConfigDict(frozen=True)

    cell: ProductionCell
    name: str
    description: str
    default: SkillSection
    sections: list[SkillSection] = Field(default_factory=list)
    prompt_version: str = ""

    def all_sections(self) -> list[SkillSection]:
        """The default + every evidence section — what the gate checks and the emitter renders."""
        return [self.default, *self.sections]

    @property
    def cited_claim_ids(self) -> set[str]:
        ids: set[str] = set()
        for s in self.all_sections():
            ids |= s.cited_ids
        return ids

    def consensus_sections(self) -> list[SkillSection]:
        return [s for s in self.sections if s.kind is SectionKind.CONSENSUS]

    def conflict_sections(self) -> list[SkillSection]:
        return [s for s in self.sections if s.kind is SectionKind.CONFLICT]

    @property
    def distinct_sources(self) -> int:
        return len({c.source_video_id for s in self.all_sections() for c in s.citations})


# ============================================================================================
# AuthoredSkill — a gated, emitted skill + its audit-facing roll-up
# ============================================================================================


def compute_skill_id(stage: str, genre: str) -> str:
    """Deterministic, cell-addressed skill id ``skl_<sha1(genre/stage)>``. Pure / idempotent."""
    basis = f"{normalize_key(genre)}/{normalize_key(stage)}"
    return f"skl_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:16]}"


def confidence_tier(default_source_count: int, *, contested: bool) -> str:
    """HIGH/MED/LOW for an opinionated default, from its DISTINCT-source corroboration (FEATURES tiers). Pure.

    A contested default is always LOW (it sits on a genuine disagreement, so it is soft guidance by
    construction); otherwise ≥3 distinct sources is HIGH, 2 is MED, 1 is LOW (one creator's habit). The
    arranger weights the skill by this — the "confidence tier PLUS the citations behind it" the project
    promised, never a bare number.
    """
    if contested:
        return "LOW"
    if default_source_count >= 3:
        return "HIGH"
    if default_source_count == 2:
        return "MED"
    return "LOW"


class AuthoredSkill(BaseModel):
    """A gate-passed, emitted SKILL.md + the metadata the registry + ``skills audit`` read (KNOW-09/11).

    The full ``body_md`` is carried so the in-memory and filesystem stores round-trip identically (the
    filesystem store ALSO writes it to ``relpath`` and records ``body_sha256``). The roll-up fields
    (``distinct_sources``, ``default_source_count``, ``default_contested``, …) are computed once from the
    draft so the human spot-audit can sample + flag without re-deriving anything.
    """

    id: str
    name: str
    description: str
    stage: str
    genre: str
    status: SkillStatus = SkillStatus.DRAFT
    relpath: str
    prompt_version: str = ""
    grounded: bool = False                 # KNOW-10: authored by decomposition + audio, not direct tutorials
    claim_ids: list[str] = Field(default_factory=list)
    citation_count: int = 0
    distinct_sources: int = 0
    default_source_count: int = 0          # corroboration behind the opinionated default
    default_contested: bool = False        # is the default sitting on a contested topic?
    consensus_topics: int = 0
    conflict_topics: int = 0
    body_sha256: str = ""
    body_md: str = ""
    authored_at: _dt.datetime
    promoted_at: Optional[_dt.datetime] = None

    @property
    def slug(self) -> str:
        return f"{normalize_key(self.genre)}-{normalize_key(self.stage)}"

    @property
    def confidence_tier(self) -> str:
        """HIGH/MED/LOW from how many DISTINCT sources back the opinionated default (FEATURES tiers).

        A single-source default is LOW (one creator's habit, not consensus); ≥3 is HIGH. The arranger
        weights the skill accordingly — exactly the "confidence tier + the citations behind it" the
        project promised instead of a bare score.

        A ``grounded`` skill (KNOW-10: composed by parent-technique decomposition + audio analysis, with no
        direct tutorials) is **LOW by construction** regardless of how many tracks corroborate its default —
        indirect, thin evidence is never presented as settled craft (PITFALLS #4).
        """
        if self.grounded:
            return "LOW"
        return confidence_tier(self.default_source_count, contested=self.default_contested)


class SkillStats(BaseModel):
    """Compact roll-up of the authored-skill layer — drives ``skills`` CLI's no-bloat ``stats`` contract."""

    total_skills: int = 0
    draft: int = 0
    promoted: int = 0
    by_stage: dict[str, int] = Field(default_factory=dict)
    by_genre: dict[str, int] = Field(default_factory=dict)
    by_confidence: dict[str, int] = Field(default_factory=dict)


# ============================================================================================
# The production-stack-of-skill grid — P1 cells + the north-star authoring order (data, reviewable)
# ============================================================================================
#
# From .planning/research/FEATURES.md "The grid (what to author, priority-tagged)". P1 = author for v1
# (directly serves the north-star fusion). Encoded with the canonical domain STAGES x GENRES labels so a
# cell here is the SAME (stage, genre) the Phase-4 claims/clusters carry. Changing a label re-buckets the
# whole grid — keep stable.

# (stage, genre) cells marked P1 in the FEATURES grid.
P1_CELLS: frozenset[tuple[str, str]] = frozenset(
    {
        # 01 Beats & rhythm — R&B, Amapiano, Deep house
        ("beats", "rnb"), ("beats", "amapiano"), ("beats", "deep-house"),
        # 02 Groove engine — the genre-defining low-rhythm element (log drum / kick+bass pump)
        ("drums", "amapiano"), ("drums", "alt-piano"), ("drums", "deep-house"),
        # 03 Basslines
        ("bassline", "rnb"), ("bassline", "amapiano"), ("bassline", "deep-house"),
        # 04 Chords / keys — lush extended (R&B); jazzy piano/Rhodes (alt-piano)
        ("chords", "rnb"), ("chords", "alt-piano"),
        # 05 Melody / leads
        ("melody", "rnb"),
        # 06 Vocals & layering — the Sonder/Brent Faiyaz stacked-harmony signature
        ("vocal-layering", "rnb"),
        # 07 Adlibs — falsetto flourishes
        ("vocals", "rnb"),
        # 10 FX / atmospheres — space/pads (R&B), airy pads (alt-piano), delay/dub space (deep house)
        ("atmosphere", "rnb"), ("atmosphere", "alt-piano"), ("atmosphere", "deep-house"),
        # 11 Arrangement
        ("arrangement", "rnb"), ("arrangement", "amapiano"), ("arrangement", "deep-house"),
        # 12 Mixing
        ("mixing", "rnb"), ("mixing", "deep-house"),
    }
)

# The signature P1 cluster — the exact north-star fusion (FEATURES: "the P1 cells cluster around exactly
# the north-star fusion"). These author ABSOLUTE first; the tuple order IS the priority.
NORTH_STAR_ORDER: tuple[tuple[str, str], ...] = (
    ("vocal-layering", "rnb"),      # stacked harmonies — the signature
    ("vocals", "rnb"),              # falsetto adlibs / flourishes
    ("chords", "rnb"),              # lush, extended chords
    ("atmosphere", "rnb"),          # space, pads
    ("drums", "amapiano"),          # the log drum (groove engine)
    ("drums", "alt-piano"),         # log drum, softer
    ("chords", "alt-piano"),        # jazzy piano / Rhodes
    ("drums", "deep-house"),        # kick + bass pump
    ("atmosphere", "deep-house"),   # delay / dub space
)
