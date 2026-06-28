"""InMemoryTrackLoader — the deterministic fake for :class:`~nameless_workers.separation_ports.TrackLoader`.

A dict from reference-track id → raw audio bytes. Lets a test inject exactly the bytes an uploaded
track "contains" without a reference-row lookup or an object store, while exercising the same
``load(reference_track_id)`` call the real loader uses.
"""

from __future__ import annotations

from uuid import UUID


class TrackNotFound(KeyError):
    """No bytes registered for the requested reference-track id."""


class InMemoryTrackLoader:
    """An in-memory map of reference-track id → audio bytes."""

    def __init__(self, tracks: dict[UUID, bytes] | None = None) -> None:
        self._tracks: dict[UUID, bytes] = dict(tracks or {})

    def put(self, reference_track_id: UUID, data: bytes) -> None:
        """Register a track's bytes (test helper; the real loader is read-only)."""
        self._tracks[reference_track_id] = data

    def load(self, reference_track_id: UUID) -> bytes:
        try:
            return self._tracks[reference_track_id]
        except KeyError as exc:
            raise TrackNotFound(reference_track_id) from exc
