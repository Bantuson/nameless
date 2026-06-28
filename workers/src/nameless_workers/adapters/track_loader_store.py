"""StoreTrackLoader — the real :class:`~nameless_workers.separation_ports.TrackLoader` (composition).

Resolves a reference-track id to its audio bytes in two pure steps:
  1. ``reference_track_id`` → ``audio_uri`` via an injected lookup (the ``reference_tracks`` row —
     the production wiring runs a one-line Postgres ``select audio_uri ...``; the lookup is injected
     so this adapter needs no DB driver of its own and stays testable).
  2. ``audio_uri`` → bytes via the SAME content-addressed :class:`~nameless_workers.ports.AudioLoader`
     the feature worker already uses (``FilesystemAudioLoader`` / ``S3AudioLoader``).

Because both collaborators are injected, this adapter imports nothing heavy and is exercised with the
existing in-memory fakes — yet in production it reuses the exact object-store path the rest of the
worker plane uses (the uploaded track's bytes are addressed by content-hash, by ID).
"""

from __future__ import annotations

from typing import Callable, Optional
from uuid import UUID

from ..ports import AudioLoader


class ReferenceTrackNotFound(KeyError):
    """The reference-track id resolved to no ``audio_uri`` (unknown / not yet uploaded)."""


class StoreTrackLoader:
    """Compose a reference-uri lookup + an object-store :class:`AudioLoader` into a track loader."""

    def __init__(
        self,
        uri_lookup: Callable[[UUID], Optional[str]],
        audio_loader: AudioLoader,
    ) -> None:
        self._uri_lookup = uri_lookup
        self._audio_loader = audio_loader

    def load(self, reference_track_id: UUID) -> bytes:
        audio_uri = self._uri_lookup(reference_track_id)
        if not audio_uri:
            raise ReferenceTrackNotFound(reference_track_id)
        return self._audio_loader.load(audio_uri)
