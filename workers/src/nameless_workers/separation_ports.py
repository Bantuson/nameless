"""Phase-8 ports — the ``typing.Protocol`` seam for the stem-separation worker (SAMP-01).

Additive to ``ports.py`` / ``reference_ports.py`` (kept separate so the Phase-8 surface stays
reviewable, matching ARCHITECTURE.md's "additive files, not edits to the locked core"). Each port has
a REAL adapter (lazy heavy imports) and a deterministic FAKE, so the whole separation flow runs in
tests with no Demucs / torch / torchaudio / object store / Postgres installed.

Ports:
  * :class:`TrackLoader`     — resolve a reference-track id to its raw audio bytes (the uploaded song
                               shared with Phase 7). Real = reference-row lookup + object store; fake =
                               an in-memory map.
  * :class:`StemSeparator`   — bytes → :class:`SeparationResult` (named stems + separator provenance).
                               Real = Demucs (htdemucs_ft / htdemucs_6s, lazy); fake = deterministic.
  * :class:`StemBlobStore`   — retain a stem's bytes by content-hash (immutable, write-if-absent). Real
                               = the S3/R2 object store; fake = an in-memory dict.
  * :class:`StemRecordStore` — persist + read the ``stems`` index rows (the Python worker is the
                               writer, mirroring how the feature worker writes ``fragment_features``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from .domain.separation import SeparationResult, StemRecord


@runtime_checkable
class TrackLoader(Protocol):
    """Load the raw audio bytes of an uploaded reference track by its id.

    The reference track is the SAME uploaded song Phase 7 analyzes for vibe (a track is both a
    reference and a sample source). The real adapter resolves ``reference_track_id`` → ``audio_uri``
    (the ``reference_tracks`` row) → bytes (object store); the fake is an in-memory map.
    """

    def load(self, reference_track_id: UUID) -> bytes: ...


@runtime_checkable
class StemSeparator(Protocol):
    """Separate a track's audio into named stems (CAP-style port; SAMP-01).

    Returns a :class:`SeparationResult` carrying the stems AND the ``separator_model`` +
    ``separator_version`` that produced them (the separation's provenance). Implementors keep Demucs
    behind this interface so a BS-RoFormer swap (STACK.md §4) is a config change, never a call-site
    change.
    """

    def separate(self, audio: bytes) -> SeparationResult: ...


@runtime_checkable
class StemBlobStore(Protocol):
    """Retain a stem's bytes by content-hash — immutable, write-if-absent (the object store role).

    ``put`` MUST be write-if-absent: the same bytes always map to the same key, so retaining an
    already-present stem is a no-op success (de-duplicating, exactly like the Rust ``ObjectStore``).
    """

    def put(self, content_hash: str, data: bytes) -> None: ...


@runtime_checkable
class StemRecordStore(Protocol):
    """Persist + read the ``stems`` index rows. The worker is the writer (mirror of Phase 2/7).

    :meth:`insert_stem` MUST be idempotent on a stem's content identity (``reference_track_id`` +
    ``audio_uri``): re-separating a track with the same deterministic model yields the same stem
    bytes → the same key → no duplicate row (matching the DB ``unique`` constraint in migration 0004).
    """

    def insert_stem(self, record: StemRecord) -> None: ...

    def list_stems(self, reference_track_id: UUID) -> list[StemRecord]: ...
