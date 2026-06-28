"""In-memory stem retention fakes — the RAM-safe doubles for the Phase-8 separation orchestration.

Two tiny fakes backing the :class:`~nameless_workers.separation_ports.StemBlobStore` and
:class:`~nameless_workers.separation_ports.StemRecordStore` ports, so the
:class:`~nameless_workers.separation_consumer.SeparationJobConsumer` runs end-to-end with no object
store and no Postgres. They model the same contracts the real adapters honor: the blob store is
write-if-absent (immutable, de-duplicating), and the record store is idempotent on a stem's content
identity (``reference_track_id`` + ``audio_uri``) — matching the DB ``unique`` constraint.
"""

from __future__ import annotations

from uuid import UUID

from ..domain.separation import StemRecord


class InMemoryStemBlobStore:
    """A content-addressed store of stem bytes (the object-store role), write-if-absent."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, content_hash: str, data: bytes) -> None:
        # Write-if-absent: the same bytes always map to the same key, so retaining twice is a no-op.
        self.blobs.setdefault(content_hash, data)

    def get(self, content_hash: str) -> bytes:
        """Read back retained bytes (test helper; the real loader is read-by-id)."""
        return self.blobs[content_hash]

    def __contains__(self, content_hash: str) -> bool:
        return content_hash in self.blobs


class InMemoryStemRecordStore:
    """An in-memory ``stems`` index — idempotent on (reference_track_id, audio_uri)."""

    def __init__(self) -> None:
        self.records: list[StemRecord] = []

    def insert_stem(self, record: StemRecord) -> None:
        # Idempotent: a stem with the same content identity is not inserted twice (mirrors the DB
        # `unique (reference_track_id, audio_uri)` constraint — a deterministic re-separation is a
        # no-op rather than a duplicated library).
        for existing in self.records:
            if (
                existing.reference_track_id == record.reference_track_id
                and existing.audio_uri == record.audio_uri
            ):
                return
        self.records.append(record)

    def list_stems(self, reference_track_id: UUID) -> list[StemRecord]:
        return [r for r in self.records if r.reference_track_id == reference_track_id]
