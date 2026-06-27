"""FixtureTranscriptFetcher — the fixture-backed :class:`~knowledge_pipeline.ports.TranscriptFetcher`.

Returns a preset :class:`CaptionFetch` per video id (availability + best transcript), defaulting to
"no captions available" for unknown videos — which is exactly what drives the ASR fallback branch in the
pipeline test. No network.
"""

from __future__ import annotations

from typing import Mapping

from ..domain.models import CaptionAvailability, CaptionFetch, VideoRef


class FixtureTranscriptFetcher:
    """A deterministic transcript fetcher over preset per-video :class:`CaptionFetch` results."""

    def __init__(self, fetches: Mapping[str, CaptionFetch]) -> None:
        self._fetches = dict(fetches)
        self.calls: list[str] = []  # record which videos were fetched (test assertions)

    def fetch(self, video: VideoRef) -> CaptionFetch:
        self.calls.append(video.video_id)
        preset = self._fetches.get(video.video_id)
        if preset is not None:
            return preset
        # Unknown video: report "no captions" so the pipeline takes the ASR fallback path.
        return CaptionFetch(
            video_id=video.video_id,
            availability=CaptionAvailability(has_manual=False, has_auto=False),
            transcript=None,
        )
