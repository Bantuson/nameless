"""Pure stem-separation helpers — content-hashing + stem-record construction. No torch, no I/O.

These are the deterministic core of the separation orchestration, kept pure so they are fully tested
without Demucs or an object store:

  * :func:`content_hash` — the SHA-256 hex of bytes, the SAME content-addressing the Rust
    ``content_hash`` (``object_store_fs.rs``) + ``FilesystemAudioLoader`` use. A stem retained under
    this key is readable by the control plane's object store with no format negotiation.
  * :func:`build_stem_records` — turn a :class:`SeparationResult` into the retained
    :class:`StemRecord` rows, content-hashing each stem and stamping the separator model+version
    provenance onto every row.

LEARNING: content-addressing is what makes separation idempotent. The stem bytes are a pure function
of (track audio, separator model) — a deterministic separator re-run produces identical bytes, hence
an identical hash, hence the same object key and the same DB row. Retention de-duplicates for free,
and a re-separation under a *different* model lands under a *different* key (so both are kept,
distinguishable by ``separator_model``).
"""

from __future__ import annotations

import hashlib
from typing import Optional
from uuid import UUID

from ..domain.separation import SeparationResult, StemRecord


def content_hash(data: bytes) -> str:
    """SHA-256 hex of ``data`` — the content-addressed object key (matches the Rust object store)."""
    return hashlib.sha256(data).hexdigest()


def build_stem_records(
    reference_track_id: UUID,
    result: SeparationResult,
    *,
    duration_ms: Optional[int] = None,
) -> list[StemRecord]:
    """Construct the retained :class:`StemRecord` rows for a separation result (pure).

    Each stem's bytes are content-hashed to its ``audio_uri``; the separator model+version are copied
    onto every record (provenance of the separation). ``duration_ms`` (if known by the caller) is
    applied uniformly. The records are returned in the separator's stem order — the caller persists
    them and retains the matching bytes under each ``audio_uri``.
    """
    records: list[StemRecord] = []
    for stem in result.stems:
        records.append(
            StemRecord(
                reference_track_id=reference_track_id,
                stem_type=stem.stem_type,
                audio_uri=content_hash(stem.audio),
                separator_model=result.separator_model,
                separator_version=result.separator_version,
                duration_ms=duration_ms,
                sample_rate=result.sample_rate or None,
            )
        )
    return records
