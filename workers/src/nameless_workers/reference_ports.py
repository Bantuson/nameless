"""Phase-7 ports — the ``typing.Protocol`` seam for the reference-analysis worker.

Additive to ``ports.py`` (kept in a separate file so the Phase-7 surface stays reviewable, matching
ARCHITECTURE.md's "additive files, not edits to the locked core"). Each port has a REAL adapter (lazy
heavy imports) and a deterministic FAKE, so the whole reference-analysis flow runs in tests with no
CLAP / librosa / pyloudnorm / LLM installed.

Ports:
  * :class:`ReferenceAnalyzer` — bytes → :class:`ReferenceContext` (NON-melodic only). The real
    adapter REUSES the Phase-2 CLAP :class:`~nameless_workers.ports.Embedder` for the style vector
    but runs a RESTRICTED feature path that never computes f0/chroma (non-cloning at extraction).
  * :class:`VibeDescriber` — measured non-melodic features → mood/space/era/texture/energy prose.
    Real = Claude (lazy ``anthropic``); fake = deterministic template.
  * :class:`GenreTagger` — CLAP zero-shot genre tag from an audio embedding (pluggable). Real ranks
    the audio embedding against text-embedded genre prompts (reuses the Embedder); fake deterministic.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .domain.models import Embedding
from .domain.reference import NonMelodicFeatures, ReferenceContext


@runtime_checkable
class ReferenceAnalyzer(Protocol):
    """Turn an uploaded reference's audio into a NON-melodic :class:`ReferenceContext` (REF-02).

    The contract is the non-cloning contract: the returned context exposes only vibe + measurable
    non-melodic targets (it is a :class:`ReferenceContext`, which structurally cannot carry melody).
    Implementors MUST NOT compute or store f0/chroma as a conditioning target.
    """

    def analyze(self, audio: bytes, reference_track_id: UUID) -> ReferenceContext: ...


@runtime_checkable
class VibeDescriber(Protocol):
    """Turn measured non-melodic features into human-facing vibe prose (mood/space/era/texture/energy).

    The output is explicitly an INTERPRETATION, kept at a different trust level than the measured
    fields (PITFALLS.md Pitfall 5) — it is never fed back as a machine conditioning target. The real
    adapter calls an LLM; it must be given only the non-melodic features (never any melody) so it
    cannot narrate a tune.
    """

    def describe(self, features: NonMelodicFeatures) -> str: ...


class GenreTag(BaseModel):
    """A zero-shot genre result: the best label (if confident) + the ranked candidate scores."""

    model_config = ConfigDict(frozen=True)

    top: Optional[str] = None
    scores: list[tuple[str, float]] = []  # (genre, cosine-similarity), descending


@runtime_checkable
class GenreTagger(Protocol):
    """Tag a track's coarse genre from its CLAP audio embedding (zero-shot, pluggable).

    "Zero-shot": rank the audio embedding against a fixed vocabulary of genre PROMPTS embedded with
    the same joint space's text tower; the nearest prompt is the tag. Verified weak for FINE-grained
    genre (PITFALLS.md Pitfall 5), so this is used for COARSE tags only, and an implementation may
    return ``top=None`` when no candidate clears a confidence margin.
    """

    def tag(self, audio_embedding: Embedding) -> GenreTag: ...
