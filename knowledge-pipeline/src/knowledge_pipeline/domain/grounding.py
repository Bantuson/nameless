"""Sparse-genre grounding domain (pydantic v2) — the Phase-6 boundary (KNOW-10).

Phases 3-5 produced authored, gate-passed Claude Skills for *well-tutorialized* cells. But some cells —
**alternative piano** (Ben Produces, Liyana Ricky, Lowbass Djy) — have almost no direct tutorials. Phase 6
authors a skill for those WITHOUT fabricating craft, using two grounding legs (PITFALLS #4/#5), each a
DISTINCT, clearly-labeled evidence type:

  1. **Decomposition** — break the under-tutorialized target into PARENT techniques that *are* taught, and
     compose the skill from the parents' already-authored, cited claims (Phase 4/5). Never invent.
  2. **Audio analysis** — run the artists' actual released tracks through the Phase-2 feature/CLAP pipeline
     and fold in the *measured* (non-melodic, surface) signatures, each cited to a real analysis record.

These types are the typed shape of that boundary, and the discipline is encoded in their structure:

  * :class:`TrackRef` — identity of a released track to analyze (the audio-source roster).
  * :class:`ClapTag` — one coarse CLAP nearest-tag + score. COARSE genre/vibe ONLY (PITFALLS #5: CLAP is
    weak for fine-grained genre), never a fine-grained craft claim.
  * :class:`AudioAnalysisRecord` — the durable, *citable* result of analyzing ONE track: the measured
    non-melodic features + the analyzer provenance. This is the audio equivalent of the Phase-3 transcript
    snapshot — **the citation an audio claim points at** ("the track is the citation"). It carries NO
    melody / chord / structure field, by construction (the cloning-boundary discipline, PITFALLS #6).
  * :class:`AudioDerivedClaim` — one atomic, *measured* assertion derived from a record, cited to that
    record. Distinct from a tutorial :class:`~knowledge_pipeline.domain.claims.Claim` at the type level so
    audio evidence is never silently presented as taught craft; :meth:`to_claim` maps it into a Phase-4
    ``Claim`` (verbatim quote = the measured statement) so the SAME Phase-5 citation gate certifies it.
  * :class:`ParentTechnique` / :class:`DecompositionMap` — the decomposition hypothesis: a target cell ->
    the parent ``(stage, genre)`` cells whose authored claims compose it, plus the *negative space* (what
    the subgenre deliberately omits/breaks vs its parents — often the real identity, PITFALLS #4).

The honesty rule (KNOW-10) lives in the confidence: a sound with NO direct tutorials is grounded by
decomposition + audio only, and is therefore **LOW confidence by construction** — thin evidence, never
settled craft. See :mod:`knowledge_pipeline.pure.confidence`.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .keys import normalize_key, normalize_text
from .models import CaptionSource, RawTranscript, TranscriptSegment
from .skills import ProductionCell


# ============================================================================================
# Track roster + audio analysis record (the durable, citable audio evidence)
# ============================================================================================


class TrackRef(BaseModel):
    """A released track to analyze — the audio-source for the sparse-genre grounding leg.

    ``audio_uri`` is the content-hash object key the real :class:`~knowledge_pipeline.ports.TrackAnalyzer`
    loads bytes by (env-gated); the fake analyzer keys its canned records on ``track_id`` and ignores it.
    """

    model_config = ConfigDict(frozen=True)

    track_id: str                          # stable slug, e.g. "ben_produces_emoyeni"
    artist: str
    title: str = ""
    genre: str = "alt-piano"               # the subgenre this track grounds
    source_track_id: Optional[str] = None  # provenance into the persistent stem/upload library (Phase 8)
    audio_uri: Optional[str] = None        # content-hash key for the real analyzer (env-gated)


class ClapTag(BaseModel):
    """One coarse CLAP nearest-tag + cosine score. COARSE vibe/genre only (PITFALLS #5)."""

    model_config = ConfigDict(frozen=True)

    tag: str
    score: float = Field(ge=-1.0, le=1.0)


class AudioAnalysisRecord(BaseModel):
    """The measured, citable signature of ONE released track — the audio equivalent of a snapshot (KNOW-10).

    INVARIANT (the measured-not-interpreted boundary, PITFALLS #5/#6): every field is a *measurement of
    surface* the DSP/CLAP pipeline genuinely makes — tempo, swing, key tendency, tonal balance, stereo
    width, loudness, and COARSE CLAP tags. There is NO melody / chord-progression / structure / "emotional
    intent" field: what we do not store, we cannot accidentally clone from or over-claim about. This record
    is what an :class:`AudioDerivedClaim` cites — ``citation_id`` is its stable anchor.
    """

    model_config = ConfigDict(frozen=True)

    # ---- identity / provenance of the analyzed track ----
    track_id: str
    artist: str
    title: str = ""
    genre: str = "alt-piano"
    source_track_id: Optional[str] = None
    region_ms: tuple[int, int] = (0, 0)    # the analyzed window [start, end] in ms

    # ---- measured non-melodic features (what audio measures WELL) ----
    tempo_bpm: float = 0.0
    swing_ratio: float = 0.0               # 0..1 groove swing (onset deviation off the straight grid)
    key_name: str = ""                     # e.g. "F:min" — tonal CENTRE, not the melodic line
    key_confidence: float = 0.0            # 0..1; low ⇒ ambiguous tonality (do not over-trust)
    tonal_balance: dict[str, float] = Field(default_factory=dict)  # {"low","mid","high"} band-energy fractions
    stereo_width: float = 0.0              # 0..1 mid/side energy ratio
    loudness_lufs: float = 0.0             # integrated LUFS (BS.1770)
    clap_tags: list[ClapTag] = Field(default_factory=list)         # coarse nearest tags (ranked)

    # ---- analyzer provenance (so a re-analysis under a different model is detectable) ----
    analyzer_version: str = "unknown"
    embed_model: str = "unknown"
    separator_model: Optional[str] = None
    analyzed_at: Optional[_dt.datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def citation_id(self) -> str:
        """The stable citation anchor an audio claim points at — ``audio:<track_id>`` ("track is the cite")."""
        return f"audio:{normalize_key(self.track_id)}"

    @property
    def region_start_ms(self) -> int:
        return int(self.region_ms[0])

    def top_tags(self, n: int = 3) -> list[str]:
        """The ``n`` highest-scoring coarse CLAP tags (genre-level only)."""
        ranked = sorted(self.clap_tags, key=lambda t: -t.score)
        return [t.tag for t in ranked[:n]]


# ============================================================================================
# Audio-derived claim (a measured assertion, cited to a record) — distinct from a tutorial Claim
# ============================================================================================


class AudioDerivedClaim(BaseModel):
    """One atomic MEASURED assertion derived from an :class:`AudioAnalysisRecord` (KNOW-10).

    Deliberately a SEPARATE type from the tutorial :class:`~knowledge_pipeline.domain.claims.Claim` so audio
    evidence is never silently laundered into "what a producer taught". ``statement`` is the verbatim,
    self-citing measured sentence (it carries its own numbers); :meth:`to_claim` lifts it into a Phase-4
    ``Claim`` whose ``quote`` IS that statement, so the same hard citation gate (KNOW-08) certifies it —
    and a record whose numbers don't back the statement is rejected exactly like a fabricated tutorial
    number. ``confidence`` is modest by design: a single track's measurement is a noisy point estimate; the
    *cross-track corroboration* (many tracks converging) is what the cluster layer turns into signal.
    """

    model_config = ConfigDict(frozen=True)

    record_id: str                         # the AudioAnalysisRecord.citation_id this is measured from
    track_id: str
    artist: str
    measure: str                           # "tempo" | "swing" | "key-tendency" | "tonal-balance" | ...
    stage: str                             # the production stage the measure informs
    technique: str                         # the (stage, technique) topic key, e.g. "groove-tempo"
    genre: list[str] = Field(default_factory=list)
    statement: str                         # the verbatim measured sentence (carries its own numbers)
    region_ms: tuple[int, int] = (0, 0)
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)

    def to_claim(self):
        """Lift this measured assertion into a Phase-4 :class:`Claim` so the Phase-5 gate certifies it. Pure.

        The ``source_video_id`` is the record's ``citation_id`` (``audio:<track>``), the ``quote`` is the
        measured ``statement`` verbatim (so the gate's quote-match + number checks pass against the audio
        snapshot), and ``caption_source`` is ``NONE`` — there is no caption; this is measured signal, and
        the ``audio:`` id prefix is what labels it as a distinct evidence kind in every citation line.

        Trust-boundary note (IN-04): because ``quote == statement`` and the synthetic snapshot segment text
        is that same ``statement``, the gate's R5 rot-check and number-vs-quote check are tautological for
        audio claims — the record IS its own source. This certifies SYNTHESIS FIDELITY (the synthesizer
        did not alter "110 bpm" into "120 bpm") but provides NO independent verification of the measurement
        itself; the trust boundary for the measured value is the analyzer, by design ("the track is the
        citation").
        """
        from .claims import Claim  # local import: domain.claims imports nothing from here (no cycle)

        return Claim(
            claim_text=self.statement,
            technique=self.technique,
            stage=self.stage,
            genre=list(self.genre),
            stance=None,
            confidence=self.confidence,
            source_video_id=self.record_id,
            timestamp_ms=int(self.region_ms[0]),
            quote=self.statement,
            caption_source=CaptionSource.NONE,
        )


def audio_snapshot(record: AudioAnalysisRecord, claims: list[AudioDerivedClaim]) -> RawTranscript:
    """Build the synthetic 'snapshot' for a record so the gate's rot-check (R5) verifies audio claims. Pure.

    The gate's deepest rule re-anchors each cited quote in the source snapshot via ``verify_citation``. An
    audio record has no transcript, so we synthesize one whose segments ARE the measured statements at the
    record's region — the durable evidence an audio citation points at. Because each claim's ``quote`` is
    its ``statement`` and a segment carries that exact text at the claim's timestamp, ``verify_citation``
    finds it and the audio citation is as auditable as a tutorial one.
    """
    start_s = round(record.region_start_ms / 1000.0, 3)
    segments = [
        TranscriptSegment(start_s=start_s, duration_s=None, text=c.statement)
        for c in claims
    ]
    return RawTranscript(
        video_id=record.citation_id,
        caption_source=CaptionSource.NONE,
        language="und",
        fetched_via=f"audio-analysis:{record.analyzer_version}",
        segments=segments,
    )


# ============================================================================================
# Decomposition — the parent-technique hypothesis (and the negative space)
# ============================================================================================


class ParentTechnique(BaseModel):
    """One parent ``(stage, genre)`` cell the target decomposes into, with the craft it contributes."""

    model_config = ConfigDict(frozen=True)

    cell: ProductionCell                   # an ALREADY-authorable parent cell (its claims compose the target)
    label: str                             # human label, e.g. "amapiano log-drum groove"
    contributes: str                       # what this parent gives the target (the rationale)


class DecompositionMap(BaseModel):
    """The decomposition hypothesis for an under-tutorialized target (KNOW-10, PITFALLS #4).

    ``parents`` are the well-taught cells whose authored claims compose the target; ``negative_space`` names
    what the subgenre deliberately omits or breaks versus those parents (density, tempo band, voicing) —
    the part decomposition is *worst* at and the part that is often the genre's real identity, so it is
    captured explicitly rather than reconstructed as "the sum of the parents".

    A decomposition is a HYPOTHESIS, not a measurement: it proposes, and the audio-analysis leg disposes
    (PITFALLS #4 "decomposition proposes; audio analysis disposes"). That epistemic status is why a
    decomposition-grounded skill is held at LOW confidence.
    """

    model_config = ConfigDict(frozen=True)

    target: ProductionCell                 # the composite cell being authored (e.g. alt-piano)
    parents: list[ParentTechnique] = Field(default_factory=list)
    negative_space: list[str] = Field(default_factory=list)
    rationale: str = ""

    def parent_cells(self) -> list[ProductionCell]:
        return [p.cell for p in self.parents]

    @property
    def parent_count(self) -> int:
        return len(self.parents)
