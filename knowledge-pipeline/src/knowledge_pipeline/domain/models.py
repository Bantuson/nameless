"""Typed domain models (pydantic v2) — the boundaries the ingestion stage reads and writes.

Five groups (the deliverable's named types are all here):
  1. **Discovery**          — ``DiscoveryQuery`` (a grid/anchor search) and ``VideoRef`` (a candidate).
  2. **Transcripts**        — ``TranscriptSegment`` + ``RawTranscript`` (timestamped, with a caption
                              source) and ``CaptionFetch`` / ``CaptionAvailability`` (what a fetch found).
  3. **Fallback**           — ``FallbackAction`` + ``FallbackDecision`` (use captions | ASR | reject).
  4. **Snapshot + scoring** — ``SnapshotRecord`` (sha256 + retrieval_date, citation-durable) and
                              ``ExtractabilityResult`` (0..1 + flags + verdict).
  5. **Corpus + reporting** — ``CorpusEntry`` (one registry row), ``CorpusStats``, ``IngestOutcome``,
                              ``IngestReport``.

Why timestamps live on every segment: Phase 4 cites claims as ``video_id @ ts``. If the snapshot did
not keep per-segment start times, that citation anchor would be unrecoverable after a takedown. The
segment timestamps ARE the citation substrate — they are load-bearing, not decoration.
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================================
# Enums — small, canonical, snake/kebab string labels (stable; downstream buckets key on them)
# ============================================================================================


class CaptionSource(str, Enum):
    """Where a transcript's text came from — the single most important quality signal (PITFALLS #1).

    Ordering of trust (encoded in :data:`CAPTION_SOURCE_WEIGHT`): ``manual`` (a human typed/checked it)
    > ``asr`` (faster-whisper — handles producer jargon + code-switching far better than YouTube's auto
    captions) > ``auto`` (YouTube auto-captions — mis-hears "log drum"/"Serato"/Hz, drops punctuation)
    > ``none`` (no spoken text recovered at all).
    """

    MANUAL = "manual"
    AUTO = "auto"
    ASR = "asr"
    NONE = "none"


class Verdict(str, Enum):
    """The extractability gate's decision on whether a source is worth distilling (KNOW-03)."""

    KEEP = "keep"            # teachable, grounded craft — admit at full weight
    LOW_SIGNAL = "low_signal"  # thin/noisy — admit DOWN-WEIGHTED and flagged, never as confident craft
    REJECT = "reject"        # nothing teachable (no captions + no ASR, or pure visual-only) — do not distil


class FallbackAction(str, Enum):
    """What the fetch+fallback decision tells the pipeline to do for one video (KNOW-03)."""

    USE_CAPTIONS = "use_captions"      # captions are good enough — no ASR needed
    FETCH_AND_ASR = "fetch_and_asr"    # captions missing/poor — pull audio + faster-whisper
    REJECT = "reject"                  # nothing usable and ASR unavailable/disabled


class IngestStatus(str, Enum):
    """The terminal status of one video's trip through the pipeline."""

    INGESTED = "ingested"                  # snapshotted + scored + registered
    SKIPPED_DUPLICATE = "skipped_duplicate"  # already in the corpus (idempotent re-run)
    REJECTED = "rejected"                  # fallback or extractability said reject — recorded, not distilled
    ERROR = "error"                        # an adapter raised; recorded for a later retry


# ============================================================================================
# 1. Discovery
# ============================================================================================


class DiscoveryQuery(BaseModel):
    """One concrete search the discovery source will run (a cell of the grid, or an artist anchor)."""

    model_config = ConfigDict(frozen=True)

    text: str                         # the literal ytsearch string, e.g. "amapiano log drum tutorial"
    kind: str = "grid"                # "grid" (genre x stage) | "artist" (anchored)
    genre: Optional[str] = None       # GENRES label this query targets (for corpus concentration)
    stage: Optional[str] = None       # STAGES label, when kind == "grid"
    artist_anchor: Optional[str] = None  # the anchor name, when kind == "artist"


class VideoRef(BaseModel):
    """A candidate tutorial surfaced by discovery — identity + provenance of HOW we found it.

    ``query_origin`` / ``genre`` / ``stage`` / ``artist_anchor`` record which grid cell or anchor
    surfaced this video, so the corpus can be inspected for north-star concentration (KNOW-04:
    "concentrated on the north-star fusion genres") rather than just counted.
    """

    model_config = ConfigDict(frozen=True)

    video_id: str
    title: str = ""
    channel: Optional[str] = None
    duration_s: Optional[int] = None
    # discovery provenance (the grid cell / anchor that found it)
    query_origin: Optional[str] = None
    genre: Optional[str] = None
    stage: Optional[str] = None
    artist_anchor: Optional[str] = None

    @property
    def url(self) -> str:
        """The (possibly-dead-after-takedown) YouTube pointer. The snapshot is the durable evidence."""
        return f"https://www.youtube.com/watch?v={self.video_id}"


# ============================================================================================
# 2. Transcripts
# ============================================================================================


class TranscriptSegment(BaseModel):
    """One timestamped line of transcript — the atomic citation anchor (``video_id @ start_s``)."""

    model_config = ConfigDict(frozen=True)

    start_s: float = Field(ge=0.0)
    text: str
    duration_s: Optional[float] = Field(default=None, ge=0.0)

    @property
    def end_s(self) -> Optional[float]:
        return None if self.duration_s is None else round(self.start_s + self.duration_s, 3)


class RawTranscript(BaseModel):
    """A fetched transcript: timestamped segments + the caption source that produced them.

    This is the unit that gets snapshotted (hashed + dated) and scored. ``full_text`` is the canonical
    join used by the scorer and the content hash — defined once so the hash is stable across callers.
    """

    video_id: str
    caption_source: CaptionSource
    language: str = "en"
    fetched_via: str = "unknown"   # which adapter path produced it ("youtube-transcript-api" | "yt-dlp-subs" | "faster-whisper")
    segments: list[TranscriptSegment] = Field(default_factory=list)

    def full_text(self) -> str:
        """Canonical whitespace-collapsed concatenation of all segment text (the scoring/hashing input)."""
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())

    def duration_s(self) -> float:
        """Best estimate of spoken span: last segment end (or start) — 0.0 if empty."""
        if not self.segments:
            return 0.0
        last = self.segments[-1]
        return float(last.end_s if last.end_s is not None else last.start_s)


class CaptionAvailability(BaseModel):
    """The cheap "what caption tracks exist" probe that :func:`fallback_decision` reasons over.

    Decoupled from the full transcript so the fallback rule is a pure function of availability +
    a cheap auto-caption quality proxy, testable in isolation.
    """

    model_config = ConfigDict(frozen=True)

    has_manual: bool = False
    has_auto: bool = False
    auto_quality: Optional[float] = None  # 0..1 cheap proxy of auto-caption quality (None if unknown/absent)


class CaptionFetch(BaseModel):
    """The result of a :class:`~knowledge_pipeline.ports.TranscriptFetcher` call.

    Carries BOTH the availability (for the fallback decision) and the best transcript actually fetched
    (manual preferred over auto), or ``None`` if only ASR can recover anything.
    """

    video_id: str
    availability: CaptionAvailability
    transcript: Optional[RawTranscript] = None


# ============================================================================================
# 3. Fallback
# ============================================================================================


class FallbackDecision(BaseModel):
    """The pure decision: which path to take for one video, and why (auditable)."""

    model_config = ConfigDict(frozen=True)

    action: FallbackAction
    caption_source: Optional[CaptionSource] = None  # which captions to use, when action == USE_CAPTIONS
    reason: str = ""


# ============================================================================================
# 4. Snapshot + extractability
# ============================================================================================


class SnapshotRecord(BaseModel):
    """Immutable evidence metadata captured AT INGEST — what makes a citation survive a takedown.

    The full timestamped segments live in the snapshot FILE (the store writes them); this record is the
    compact, registry-stored fingerprint: the content ``sha256`` (so tampering/drift is detectable when
    the snapshot file is re-read — ``load_snapshot`` re-hashes and rejects a mismatch), the
    ``retrieval_date`` (injected — never ``datetime.now()`` inside the pure function), and the span
    bounds. ``content_sha256`` + ``retrieval_date`` together are the "I saw exactly this text on this
    date" attestation a dead YouTube URL can no longer provide.
    """

    model_config = ConfigDict(frozen=True)

    video_id: str
    content_sha256: str
    retrieval_date: _dt.datetime
    caption_source: CaptionSource
    language: str = "en"
    segment_count: int = 0
    char_count: int = 0
    first_segment_s: Optional[float] = None
    last_segment_s: Optional[float] = None


class ExtractabilityResult(BaseModel):
    """The per-source extractability gate output (KNOW-03) — a 0..1 score, its components, and flags.

    The score is NOT a vanity metric; it is a *gate*: it decides whether a transcript is teachable craft
    or filler, BEFORE any distillation runs. The component sub-scores are kept so a low score is
    explainable ("low_word_density + visual_only", not just "0.21"). ``flags`` and ``verdict`` are the
    machine-actionable outputs the pipeline registers and the CLI groups by.
    """

    model_config = ConfigDict(frozen=True)

    video_id: str
    score: float = Field(ge=0.0, le=1.0)
    verdict: Verdict
    # component sub-scores (each 0..1) — what the weighted score is built from
    caption_source_weight: float
    word_density: float
    vocab_presence: float
    actionable_ratio: float
    visual_only_penalty: float   # 0..1 — how much the score was attenuated for visual-only signal
    # raw counts (for transparency / Phase-4 reuse)
    word_count: int = 0
    vocab_hits: int = 0
    flags: list[str] = Field(default_factory=list)


# ============================================================================================
# 5. Corpus + reporting
# ============================================================================================


class CorpusEntry(BaseModel):
    """One row of the corpus registry: the video + its snapshot fingerprint + its extractability.

    This is what ``corpus list`` / ``corpus show`` read, and what Phase 4 iterates to mine claims.
    It carries NO transcript text (that is in the snapshot file, loaded by ID on demand) — keeping the
    registry lean and the listing token-cheap.
    """

    video: VideoRef
    snapshot: SnapshotRecord
    extractability: ExtractabilityResult
    ingested_at: _dt.datetime


class CorpusStats(BaseModel):
    """A compact roll-up of the corpus — drives KNOW-04's "is it 100+ and north-star-concentrated?"."""

    total: int = 0
    by_verdict: dict[str, int] = Field(default_factory=dict)
    by_genre: dict[str, int] = Field(default_factory=dict)
    by_caption_source: dict[str, int] = Field(default_factory=dict)


class IngestOutcome(BaseModel):
    """The compact result of pushing ONE video through the pipeline — safe to log/print."""

    model_config = ConfigDict(frozen=True)

    video_id: str
    status: IngestStatus
    verdict: Optional[Verdict] = None
    score: Optional[float] = None
    caption_source: Optional[CaptionSource] = None
    detail: str = ""


class IngestReport(BaseModel):
    """The roll-up of an ingest run — counts per status + the per-video outcomes."""

    outcomes: list[IngestOutcome] = Field(default_factory=list)

    def count(self, status: IngestStatus) -> int:
        return sum(1 for o in self.outcomes if o.status is status)

    @property
    def ingested(self) -> int:
        return self.count(IngestStatus.INGESTED)

    @property
    def rejected(self) -> int:
        return self.count(IngestStatus.REJECTED)

    @property
    def skipped(self) -> int:
        return self.count(IngestStatus.SKIPPED_DUPLICATE)

    @property
    def errored(self) -> int:
        return self.count(IngestStatus.ERROR)
