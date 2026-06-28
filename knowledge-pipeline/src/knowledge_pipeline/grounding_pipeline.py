"""GroundingPipeline — the Phase-6 orchestration, pure over injected ports (KNOW-10).

The last knowledge-pipeline phase. It authors a skill for an UNDER-tutorialized cell (alternative piano)
without fabricating craft, by fusing the two grounding legs the research prescribes (PITFALLS #4/#5) and
running the result through the SAME Phase-5 machinery (fake synthesizer + hard citation gate + skill store)
— the model and the audio get no special pass. Like every other pipeline here it contains NO ``anthropic``,
NO torch/CLAP, NO sqlite-of-its-own: every dependency is a port, so the whole flow runs on fakes/fixtures.

    decomp   = decompose(target)                              [KNOW-10: the parent hypothesis]
    parents  = claims for decomp.parent_cells (claim_store)   [the taught, cited evidence]
    for track in tracks:                                      [the audio-analysis leg]
        record = analyzer.analyze(track)                      [Phase-2 features/CLAP — or the fake]
        audio += [adc.to_claim() for adc in audio_derived_claims(record)]   [measured, self-citing]
    clusters = cross_reference(parents + audio)               [corroboration across tutorials AND tracks]
    draft    = synthesizer.synthesize(target, clusters)       [Phase-5 fake synthesizer, relabelled]
    gate     = citation_gate(draft, all_claims, snapshots)    [KNOW-08: invented/untraceable ⇒ REJECT]
    if gate.ok:                                               [confidence is LOW by construction (KNOW-10)]
        skill = build_grounded_skill(draft, decomp, records, LOW)   [grounded emitter, honest stamp]
        store.upsert_skill(skill)

The defining honesty point (KNOW-10): the emitted skill is stamped **LOW confidence** with an explicit
"grounded by decomposition + audio analysis, NOT direct tutorials" note — even though its default may rest
on three corroborating tracks. Thin, indirect evidence is never dressed as settled craft.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from pydantic import BaseModel, Field

from .domain.claims import Claim
from .domain.grounding import (
    AudioAnalysisRecord,
    AudioDerivedClaim,
    DecompositionMap,
    TrackRef,
    audio_snapshot,
)
from .domain.models import RawTranscript
from .domain.skills import AuthoredSkill, ProductionCell, SkillDraft, SkillStatus, compute_skill_id
from .ports import ClaimStore, CorpusStore, SkillStore, SkillSynthesizer, TrackAnalyzer
from .pure.audio_claims import audio_derived_claims
from .pure.citation_gate import GateResult, citation_gate
from .pure.confidence import grounding_confidence, grounding_note
from .pure.cross_reference import cross_reference
from .pure.decompose import ALT_PIANO_TARGET, decompose
from .pure.grounded_emitter import emit_grounded_skill_md

logger = logging.getLogger("knowledge_pipeline.grounding")


@dataclass
class GroundingConfig:
    """Knobs for one grounding run."""

    gate_min_coverage: float = 0.6     # the ungrounded-assertion coverage floor for the gate


class GroundingOutcome(BaseModel):
    """Compact result of grounding one target — safe to log/print (no SKILL.md body dump)."""

    target: str
    status: str                        # authored | rejected
    skill_id: Optional[str] = None
    confidence: str = ""
    parent_cells: list[str] = Field(default_factory=list)
    tutorial_sources: int = 0
    audio_tracks: int = 0
    citation_count: int = 0
    distinct_sources: int = 0
    reasons: list[str] = Field(default_factory=list)


def _direct_tutorial_sources(parent_claims: Sequence[Claim], target: ProductionCell) -> int:
    """Distinct TUTORIAL sources that teach the target subgenre DIRECTLY (≈0 for alt-piano). Pure.

    Counts only non-audio claims whose evidenced genre is the target's own genre — i.e. real direct
    tutorial coverage of the sparse subgenre, which is exactly what is missing. Audio ``audio:`` ids and
    parent-genre claims (amapiano/rnb/deep-house) do NOT count as direct coverage.
    """
    target_genres = {target.genre, target.genre.replace("alternative-", "alt-")}
    sources = {
        c.source_video_id
        for c in parent_claims
        if not c.source_video_id.startswith("audio:") and (set(c.genre) & target_genres)
    }
    return len(sources)


def build_grounded_skill(
    draft: SkillDraft,
    decomposition: DecompositionMap,
    records: Sequence[AudioAnalysisRecord],
    *,
    confidence: str,
    note: str,
    status: SkillStatus = SkillStatus.DRAFT,
    now: _dt.datetime,
) -> AuthoredSkill:
    """Assemble the grounded :class:`AuthoredSkill` (LOW by construction) from a gated draft. Pure (KNOW-10)."""
    body_md = emit_grounded_skill_md(
        draft, decomposition, records, status=status, confidence=confidence, grounding_note=note
    )
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
        grounded=True,                                  # KNOW-10: LOW by construction
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


class GroundingPipeline:
    """Orchestrates decompose -> parents -> audio -> synthesize -> GATE -> grounded emit. Stateless."""

    def __init__(
        self,
        synthesizer: SkillSynthesizer,
        skill_store: SkillStore,
        claim_store: ClaimStore,
        track_analyzer: TrackAnalyzer,
        tracks: Sequence[TrackRef],
        *,
        corpus: Optional[CorpusStore] = None,
        config: Optional[GroundingConfig] = None,
        now: Optional[Callable[[], _dt.datetime]] = None,
    ) -> None:
        self._synth = synthesizer
        self._store = skill_store
        self._claims = claim_store
        self._analyzer = track_analyzer
        self._tracks = list(tracks)
        self._corpus = corpus
        self._config = config or GroundingConfig()
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))

    # ---- parent gathering ----
    def _parent_claims(self, decomposition: DecompositionMap) -> list[Claim]:
        """Claims for the decomposition's parent cells (same stage, parent genre in the claim's genres)."""
        wanted = {(p.cell.stage, p.cell.genre) for p in decomposition.parents}
        out: list[Claim] = []
        for c in self._claims.list_claims():
            for (stage, genre) in wanted:
                if c.stage == stage and genre in (c.genre or []):
                    out.append(c)
                    break
        return out

    # ---- audio leg ----
    def _analyze_tracks(
        self,
    ) -> tuple[list[Claim], list[AudioAnalysisRecord], dict[str, RawTranscript]]:
        """Analyze each track BEST-EFFORT (WR-03/WR-04).

        Policy is explicit: a track that fails to analyze (missing/corrupt file, decode error, worker API
        error) or that yields no audio-derived claims is logged at WARNING and SKIPPED — never aborting the
        whole grounding run because one file of many is bad. The caller (:meth:`ground`) then REQUIRES at
        least one surviving record before authoring, so a roster that fully drops cannot ship a skill that
        claims audio corroboration it never actually used.
        """
        audio_claims: list[Claim] = []
        records: list[AudioAnalysisRecord] = []
        snapshots: dict[str, RawTranscript] = {}
        for track in self._tracks:
            try:
                record = self._analyzer.analyze(track)
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole run (WR-04)
                logger.warning("audio analysis FAILED for track %s; skipping: %s", track.track_id, exc)
                continue
            adcs: list[AudioDerivedClaim] = audio_derived_claims(record)
            if not adcs:
                logger.warning(
                    "track %s produced no audio-derived claims; skipping (no corroboration) (WR-03)",
                    track.track_id,
                )
                continue
            records.append(record)
            audio_claims.extend(adc.to_claim() for adc in adcs)
            snapshots[record.citation_id] = audio_snapshot(record, adcs)
        return audio_claims, records, snapshots

    def _parent_snapshots(self, parent_claims: Sequence[Claim]) -> dict[str, RawTranscript]:
        """Load the Phase-3 snapshots for the parent claims' source videos (for the gate's R5 rot check)."""
        if self._corpus is None:
            return {}
        out: dict[str, RawTranscript] = {}
        for vid in {c.source_video_id for c in parent_claims}:
            snap = self._corpus.load_snapshot(vid)
            if snap is not None:
                out[vid] = snap
        return out

    def ground(self, target: ProductionCell = ALT_PIANO_TARGET) -> GroundingOutcome:
        """Decompose -> gather parents -> analyze tracks -> synthesize -> GATE -> emit grounded skill."""
        self._store.init_schema()
        cfg = self._config

        decomposition = decompose(target)
        parent_claims = self._parent_claims(decomposition)
        audio_claims, records, audio_snaps = self._analyze_tracks()
        parent_cell_slugs = [p.cell.slug for p in decomposition.parents]

        # WR-03: the grounded path is decomposition AND measured audio. If every track failed or yielded no
        # claims (or the roster was empty), there is NO audio corroboration — refuse rather than ship a
        # skill whose banner/description claim a measured-track leg it never used.
        if not records:
            logger.warning(
                "GROUNDING REJECTED %s: no audio-analysis records (every track failed or yielded no claims)",
                target.slug,
            )
            return GroundingOutcome(
                target=target.slug, status="rejected", parent_cells=parent_cell_slugs, audio_tracks=0,
                reasons=["grounded path requires >=1 successfully analyzed track; none survived"],
            )

        all_claims = parent_claims + audio_claims
        if not all_claims:
            return GroundingOutcome(
                target=target.slug, status="rejected",
                parent_cells=[p.cell.slug for p in decomposition.parents],
                reasons=["no parent or audio evidence to compose from"],
            )

        clusters = cross_reference(all_claims)
        draft = self._synth.synthesize(target, clusters)
        draft = self._relabel(draft, decomposition, len(records))

        claim_index = {c.id: c for c in all_claims}
        snapshots = {**self._parent_snapshots(parent_claims), **audio_snaps}

        result: GateResult = citation_gate(
            draft, claim_index, snapshots=snapshots, min_coverage=cfg.gate_min_coverage
        )
        direct = _direct_tutorial_sources(parent_claims, target)

        if not result.ok:
            logger.warning("GROUNDING REJECTED %s: %s", target.slug, "; ".join(result.reasons))
            return GroundingOutcome(
                target=target.slug, status="rejected", parent_cells=parent_cell_slugs,
                tutorial_sources=direct, audio_tracks=len(records), reasons=result.reasons,
            )

        confidence = grounding_confidence(
            direct_tutorial_sources=direct,
            parent_techniques=decomposition.parent_count,
            audio_track_count=len(records),
        )
        note = grounding_note(decomposition, audio_track_count=len(records), confidence=confidence)
        skill = build_grounded_skill(
            draft, decomposition, records,
            confidence=confidence, note=note, status=SkillStatus.DRAFT, now=self._now(),
        )
        self._store.upsert_skill(skill)
        logger.info("grounded %s as %s (confidence=%s)", target.slug, skill.id, confidence)
        return GroundingOutcome(
            target=target.slug, status="authored", skill_id=skill.id, confidence=confidence,
            parent_cells=parent_cell_slugs, tutorial_sources=direct, audio_tracks=len(records),
            citation_count=skill.citation_count, distinct_sources=skill.distinct_sources,
        )

    def _relabel(
        self, draft: SkillDraft, decomposition: DecompositionMap, track_count: int
    ) -> SkillDraft:
        """Override the synthesizer's generic name/description with the grounded composite framing. Pure."""
        parents = " + ".join(p.label for p in decomposition.parents)
        name = decomposition.target.genre  # "alternative-piano"
        description = (
            f"Alternative-piano (private-school amapiano) production craft, GROUNDED — composed by "
            f"decomposition into {parents} and corroborated against {track_count} measured track(s). "
            "LOW confidence (under-tutorialized; not from direct tutorials). Load when arranging or "
            "mixing alternative piano."
        )
        return draft.model_copy(update={"name": name, "description": description})
