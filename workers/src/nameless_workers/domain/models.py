"""Typed domain models (pydantic v2) — the boundaries the worker reads and writes.

Three groups:
  1. **Job envelope** — ``FeatureExtractJob`` / ``SeparateJob`` mirror the Rust ``JobEnvelope`` JSON
     byte-for-byte (internally tagged on ``job``), so a payload Rust enqueued round-trips here.
  2. **Features & embeddings** — ``AudioFeatures`` (CAP-03) and ``Embedding`` (CAP-04): the typed
     output of the extractor/embedder, persisted to ``fragment_features`` + the vector columns.
  3. **Compact read models** — ``FragmentRecord`` (what the worker reads about a fragment: NO vectors)
     and ``SearchHit`` (the compact retrieval result: id + key + tempo + score, never arrays).

The compact-output contract (PRD §12) is enforced at the *type* level: ``SearchHit`` has no field that
can carry a vector or a feature array, so the CLI physically cannot print one.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================================
# 1. Job envelope — mirrors nameless_core::job::JobEnvelope
# ============================================================================================
# Rust: `#[serde(tag = "job", rename_all = "snake_case")]` over a 2-variant enum, e.g.
#   {"job": "feature_extract", "fragment_id": "<uuid>"}
# pydantic reproduces that with a discriminated union on the literal `job` tag.


class FeatureExtractJob(BaseModel):
    """Compute f0/chroma/onsets/key/LUFS + embeddings for a captured fragment (the Phase-2 job)."""

    model_config = ConfigDict(frozen=True)
    job: Literal["feature_extract"] = "feature_extract"
    fragment_id: UUID


class SeparateJob(BaseModel):
    """Separate a fragment into stems (a fragment-keyed Phase-8 variant; modelled here for parity)."""

    model_config = ConfigDict(frozen=True)
    job: Literal["separate"] = "separate"
    fragment_id: UUID


class SeparateTrackJob(BaseModel):
    """Separate an uploaded reference TRACK into its retained stem library (the Phase-8 job, SAMP-01).

    Mirrors Rust ``JobEnvelope::SeparateTrack`` byte-for-byte:
    ``{"job": "separate_track", "reference_track_id": "<uuid>"}``. Handled by the
    ``SeparationJobConsumer`` driving the ``DemucsStemSeparator``. Keyed by the reference track (the
    same uploaded audio Phase 7 analyzes) — a track is both reference + sample source.
    """

    model_config = ConfigDict(frozen=True)
    job: Literal["separate_track"] = "separate_track"
    reference_track_id: UUID


class AnalyzeReferenceJob(BaseModel):
    """Extract NON-melodic reference context for an uploaded reference track (the Phase-7 job).

    Mirrors Rust ``JobEnvelope::AnalyzeReference`` byte-for-byte:
    ``{"job": "analyze_reference", "reference_track_id": "<uuid>"}``. Handled by the
    ``RestrictedReferenceAnalyzer``, which never computes f0/chroma (the non-cloning path).
    """

    model_config = ConfigDict(frozen=True)
    job: Literal["analyze_reference"] = "analyze_reference"
    reference_track_id: UUID


# The tagged union, discriminated on `job` — the exact shape Rust serializes.
JobEnvelope = Annotated[
    Union[FeatureExtractJob, SeparateJob, SeparateTrackJob, AnalyzeReferenceJob],
    Field(discriminator="job"),
]


# ============================================================================================
# 2. Features & embeddings
# ============================================================================================


class F0Contour(BaseModel):
    """The fundamental-frequency contour from torchcrepe — melody as a continuous signal (PRD §8).

    Parallel arrays sampled at a fixed hop. ``confidence`` is CREPE's periodicity (0..1); frames below
    a voicing threshold are where the contour is unreliable (silence / unvoiced / noise).
    """

    times_s: list[float] = Field(default_factory=list)
    f0_hz: list[float] = Field(default_factory=list)
    confidence: list[float] = Field(default_factory=list)


class KeyEstimate(BaseModel):
    """The musical key, from Krumhansl-Schmuckler chroma-template correlation (pure; see pure/key.py)."""

    tonic_pc: int = Field(ge=0, le=11)  # pitch class 0=C … 11=B
    mode: Literal["maj", "min"]
    name: str  # canonical label, e.g. 'C:maj' / 'A:min'
    correlation: float  # the winning Pearson correlation (−1..1); low ⇒ ambiguous tonality


class AudioFeatures(BaseModel):
    """Everything the DSP stage derives from one fragment's audio (CAP-03).

    Large arrays (``f0_contour``, ``chroma``) live here and in ``fragment_features``; they are NEVER
    surfaced by the CLI. Only the scalar summaries (``tempo_bpm``, ``key``, ``loudness_lufs``) are
    compact enough to show.
    """

    # melody / harmony as signals
    f0_contour: F0Contour = Field(default_factory=F0Contour)
    chroma: list[list[float]] = Field(default_factory=list)  # 12 × T (row per pitch class)
    chroma_mean: list[float] = Field(default_factory=list)  # 12-d, what key estimation runs on
    # rhythm as event times
    onsets_s: list[float] = Field(default_factory=list)
    beat_grid_s: list[float] = Field(default_factory=list)
    tempo_bpm: float = 0.0
    # tonality + loudness
    key: KeyEstimate
    loudness_lufs: float = 0.0
    # reconstruction / provenance metadata
    sample_rate: int = 0
    duration_s: float = 0.0
    hop_length: int = 0
    analyzer_version: str = "unknown"


class Embedding(BaseModel):
    """A single dense vector + the model that produced it. Used for both the audio and note towers."""

    model_config = ConfigDict(frozen=True)
    model_name: str
    dim: int
    vector: list[float]


# ============================================================================================
# 3. Compact read / result models  (NO vectors, NO arrays — the token-strategy boundary)
# ============================================================================================


class FragmentRecord(BaseModel):
    """The compact slice of a fragment the worker reads to analyze it — never any feature array.

    Mirrors the subset of ``nameless_core::fragment::Fragment`` the worker needs: identity, the
    provenance that selects the lifecycle path, the current state (for idempotency), the content-hash
    ``audio_uri`` to load bytes by, and the ``note_text`` to embed.
    """

    id: UUID
    project_id: UUID
    kind: str
    provenance: str  # canonical label; parsed to Provenance at the edge
    state: str  # canonical label; parsed to FragmentState at the edge
    audio_uri: str  # SHA-256 content-hash object key
    note_text: str
    duration_ms: Optional[int] = None
    sample_rate: Optional[int] = None


class SearchHit(BaseModel):
    """One compact retrieval result: id + key + tempo + score. Structurally cannot carry a vector."""

    model_config = ConfigDict(frozen=True)
    fragment_id: UUID
    key: Optional[str] = None
    tempo_bpm: Optional[float] = None
    score: float  # cosine similarity in [−1, 1]; higher = closer


class AnalyzeOutcome(BaseModel):
    """The compact result of analyzing one fragment — returned by the consumer, safe to log/print."""

    model_config = ConfigDict(frozen=True)
    fragment_id: UUID
    from_state: str
    to_state: str
    key: Optional[str] = None
    tempo_bpm: Optional[float] = None
    loudness_lufs: Optional[float] = None
    audio_embedding_dim: Optional[int] = None
    note_embedding_dim: Optional[int] = None
    skipped: bool = False  # True when the fragment was already analyzed (idempotent redelivery)
