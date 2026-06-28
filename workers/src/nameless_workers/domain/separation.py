"""Stem-separation domain models (pydantic v2) — the persistent stem library, typed (SAMP-01).

A producer separates any uploaded reference track into named stems (Demucs), and every stem is kept
forever in object storage, browsable per track. A stem can later be promoted to an attributed
`sampled` fragment (the Rust control plane owns that promotion + the attribution gate; this module
only models the SEPARATION half: what comes out of Demucs and what gets retained).

Mirrors the Rust types in ``crates/nameless-core/src/stems.rs``:
  * :class:`StemType`   ↔ ``StemType``       (vocals|drums|bass|other|piano|guitar)
  * :class:`StemRecord` ↔ ``Stem`` index row (reference_track_id, stem_type, audio_uri,
                                              separator_model+version — the separation's provenance)

The audio bytes themselves are addressed by content-hash uri (immutable, by ID — never inline in a
record), exactly like a fragment's audio. The separator model+version travel on every record so a
re-separation under a better model (BS-RoFormer swap, STACK.md §4) is auditable.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StemType(str, Enum):
    """The named source a stem isolates — the fixed Demucs output vocabulary (mirror of Rust).

    ``htdemucs`` / ``htdemucs_ft`` emit the four-stem set; ``htdemucs_6s`` additionally isolates
    piano + guitar (directly relevant to alt-piano sampling). Values are the canonical snake_case DB
    labels and MUST match the Rust ``StemType::as_str`` byte-for-byte.
    """

    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    OTHER = "other"
    PIANO = "piano"
    GUITAR = "guitar"

    @classmethod
    def from_db_str(cls, s: str) -> "StemType":
        """Parse a canonical label; raises ``ValueError`` on an unknown label (no silent default)."""
        return cls(s)


# The four stems every htdemucs / htdemucs_ft separation produces, in canonical order.
HTDEMUCS_4: tuple[StemType, ...] = (
    StemType.VOCALS,
    StemType.DRUMS,
    StemType.BASS,
    StemType.OTHER,
)
# htdemucs_6s adds piano + guitar.
HTDEMUCS_6: tuple[StemType, ...] = HTDEMUCS_4 + (StemType.PIANO, StemType.GUITAR)


class SeparatedStem(BaseModel):
    """One isolated stem straight out of the separator: its type + the raw (encoded) audio bytes.

    ``audio`` is the lowest-common-denominator carrier — WAV/PCM bytes the real Demucs adapter
    encodes per stem, or deterministic bytes from the fake. The orchestration content-hashes these
    bytes to produce the retained object key.
    """

    model_config = ConfigDict(frozen=True)

    stem_type: StemType
    audio: bytes


class SeparationResult(BaseModel):
    """The full output of one separation: the stems + the provenance of HOW they were isolated.

    ``separator_model`` (e.g. ``htdemucs_ft`` / ``htdemucs_6s``) and ``separator_version`` (e.g.
    ``4.0.1``) are recorded on every retained stem so the credits sheet can be honest about the tool
    and a re-separation under a different model is detectable.
    """

    model_config = ConfigDict(frozen=True)

    separator_model: str
    separator_version: str
    stems: list[SeparatedStem]
    sample_rate: int = 0

    def stem_types(self) -> list[StemType]:
        """The stem types produced, in order (handy for assertions / the outcome summary)."""
        return [s.stem_type for s in self.stems]


class StemRecord(BaseModel):
    """A retained stem index row — mirror of the Rust ``Stem`` (what the worker persists to ``stems``).

    ``audio_uri`` is the SHA-256 content-hash of the stem bytes (the object key the bytes are stored
    under, matching the Rust ``content_hash`` / ``FilesystemObjectStore`` layout). NO provenance /
    state / kind — a stem is not a fragment until the control plane promotes it.
    """

    model_config = ConfigDict(frozen=True)

    reference_track_id: UUID
    stem_type: StemType
    audio_uri: str
    separator_model: str
    separator_version: str
    duration_ms: Optional[int] = None
    sample_rate: Optional[int] = None
