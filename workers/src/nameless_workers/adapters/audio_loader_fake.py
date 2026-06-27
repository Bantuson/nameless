"""InMemoryAudioLoader — the deterministic fake for :class:`~nameless_workers.ports.AudioLoader`.

A dict from content-hash id → bytes. Lets tests inject exactly the bytes a fragment "contains" without
any object store, while exercising the same ``load(audio_uri)`` call the real loader uses.
"""

from __future__ import annotations


class AudioNotFound(KeyError):
    """No bytes registered for the requested content-hash id."""


class InMemoryAudioLoader:
    """An in-memory content-addressed store of audio bytes."""

    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self._blobs: dict[str, bytes] = dict(blobs or {})

    def put(self, audio_uri: str, data: bytes) -> None:
        """Register bytes under a content-hash id (test helper; the real loader is read-only)."""
        self._blobs[audio_uri] = data

    def load(self, audio_uri: str) -> bytes:
        try:
            return self._blobs[audio_uri]
        except KeyError as exc:
            raise AudioNotFound(audio_uri) from exc
