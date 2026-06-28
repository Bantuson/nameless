"""Reference-track context models (pydantic v2) — VIBE + measurable NON-melodic targets only.

A producer uploads a finished song; the worker extracts its *vibe* and *measurable non-melodic sonic
targets* as project conditioning context. The hard product line (REF-03, PITFALLS.md Pitfall 6):
*imitate the vibe* must never become *reproduce the song*.

## The structural non-cloning guarantee, at the type level

:class:`NonMelodicFeatures` is the headline type. It declares ONLY non-melodic fields and is sealed
with ``extra="forbid"`` — so a developer (or a careless analyzer) **cannot even construct it** with
an ``f0`` / ``chroma`` / ``melody`` field: pydantic raises ``ValidationError`` on the unknown key.
What the type cannot carry, generation cannot clone. This mirrors the Rust ``ReferenceContext``,
which has no melodic column, and the ``gather_melodic_conditioning`` compile-time barrier — three
expressions of one guarantee across the stack.

The compact :class:`ReferenceContextSummary` is what the CLI/agent surface sees: it carries the
embedding's *dimension* (an int), never the vector, and — like everything here — no melodic field.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import Embedding

# Names a reference's context must NEVER carry — the melodic/structural surface that would enable
# cloning. Used by the type sealing here and by the runtime tripwire in pure/non_melodic.py.
FORBIDDEN_MELODIC_FIELDS: frozenset[str] = frozenset(
    {
        "f0",
        "f0_contour",
        "chroma",
        "chroma_mean",
        "melody",
        "notes",
        "note",
        "pitch",
        "pitches",
        "chord",
        "chords",
        "key",
        "structure",
        "arrangement",
        "midi",
    }
)


class TonalBalance(BaseModel):
    """Coarse 5-band energy balance — *where the energy sits*, NOT the notes (PITFALLS.md Pitfall 5).

    Five broad frequency regions whose ratios sum to ~1.0. This is a spectral-SHAPE descriptor (a mix
    target: "bright? bass-heavy?"), deliberately too coarse to encode a melody or chord — the 12
    chroma pitch classes are folded away into 5 frequency bands. Computed by ``pure/tonal_balance.py``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float = Field(ge=0.0)  # ~20–120 Hz (sub)
    low_mid: float = Field(ge=0.0)  # ~120–500 Hz (body)
    mid: float = Field(ge=0.0)  # ~500–2k Hz (presence)
    high_mid: float = Field(ge=0.0)  # ~2k–6k Hz (definition)
    high: float = Field(ge=0.0)  # ~6k–20k Hz (air)

    def bands(self) -> list[float]:
        """The five band ratios in low→high order."""
        return [self.low, self.low_mid, self.mid, self.high_mid, self.high]

    def total(self) -> float:
        """Sum of the band ratios (≈1.0 when normalized)."""
        return sum(self.bands())


class NonMelodicFeatures(BaseModel):
    """Everything the RESTRICTED reference analyzer measures — and structurally nothing melodic.

    Sealed with ``extra="forbid"``: constructing this with an ``f0``/``chroma``/``melody`` key raises
    a ``ValidationError``. The type *cannot* carry a melody, so a reference's tune is never
    materialized as a conditioning target. Every field below is a global, non-melodic descriptor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tonal_balance: TonalBalance
    stereo_width: float = Field(ge=0.0, le=1.0)  # mid/side ratio; 0=mono, ~0.5=decorrelated, →1=anti-phase
    lufs: float  # integrated loudness (ITU-R BS.1770-4); a mastering target
    tempo_bpm_min: float = Field(ge=0.0)  # tempo as a RANGE (target band), not a beat grid
    tempo_bpm_max: float = Field(ge=0.0)
    genre: Optional[str] = None  # coarse zero-shot tag (CLAP) — a label, not structure
    sample_rate: int = 0
    duration_s: float = 0.0


class ReferenceContext(BaseModel):
    """The full extracted reference context (REF-02) — the analyzer's output, persisted to Postgres.

    Carries the CLAP *style* embedding (advisory vibe vector, addressed by ID — never printed), the
    sealed :class:`NonMelodicFeatures`, and the LLM ``vibe_description`` prose (an interpretation, a
    *different trust level* than the measured fields — never a machine conditioning target). There is
    no melodic field anywhere in this object or its components.
    """

    model_config = ConfigDict(extra="forbid")

    reference_track_id: UUID
    style_embedding: Embedding  # CLAP audio-tower vector; a global vibe fingerprint, not a melody
    non_melodic: NonMelodicFeatures
    vibe_description: str
    analyzer_version: str

    def summary(self) -> "ReferenceContextSummary":
        """Project to the compact, array-free view the CLI/agent is allowed to see.

        Drops the embedding vector (keeps only its dimension) so the large array never enters agent
        context — the token-strategy boundary, enforced at the type level: the summary has no field
        that can hold a vector or a melody.
        """
        nm = self.non_melodic
        return ReferenceContextSummary(
            reference_track_id=self.reference_track_id,
            genre=nm.genre,
            tempo_bpm_min=nm.tempo_bpm_min,
            tempo_bpm_max=nm.tempo_bpm_max,
            lufs=nm.lufs,
            tonal_balance=nm.tonal_balance,
            stereo_width=nm.stereo_width,
            vibe_description=self.vibe_description,
            embedding_dim=self.style_embedding.dim,
            analyzer_version=self.analyzer_version,
        )


class ReferenceContextSummary(BaseModel):
    """The compact, array-free view of a :class:`ReferenceContext` (for `reference show`).

    Carries ``embedding_dim`` (an int) instead of the vector, and — like the rest of the type — no
    melodic field. Whatever the surface does, it cannot print the style vector or a melody.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_track_id: UUID
    genre: Optional[str] = None
    tempo_bpm_min: float
    tempo_bpm_max: float
    lufs: float
    tonal_balance: TonalBalance
    stereo_width: float
    vibe_description: str
    embedding_dim: int  # dimension of the (un-exposed) CLAP style embedding — a count, not the vector
    analyzer_version: str
