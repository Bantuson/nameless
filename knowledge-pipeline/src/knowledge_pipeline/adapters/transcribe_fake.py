"""FixedTextTranscriber — the deterministic :class:`~knowledge_pipeline.ports.Transcriber` for tests.

Stands in for faster-whisper: returns a preset ASR :class:`RawTranscript` per video id (or a default
one-segment transcript) with ``caption_source = asr``. Lets the ASR FALLBACK BRANCH of the pipeline be
exercised end-to-end with no model and no audio — proving that "no captions -> fetch+ASR -> snapshot ->
score" actually works, which is the whole point of KNOW-03.
"""

from __future__ import annotations

from typing import Mapping, Optional

from ..domain.models import CaptionSource, RawTranscript, TranscriptSegment, VideoRef


class FixedTextTranscriber:
    """A deterministic ASR stand-in over preset per-video transcripts."""

    def __init__(
        self,
        transcripts: Optional[Mapping[str, RawTranscript]] = None,
        *,
        default_text: str = "high pass the log drum around thirty hertz then sidechain the bass to the kick",
    ) -> None:
        self._transcripts = dict(transcripts or {})
        self._default_text = default_text
        self.calls: list[str] = []  # which videos got transcribed (test assertions / ASR-was-invoked proof)

    def transcribe(self, video: VideoRef) -> RawTranscript:
        self.calls.append(video.video_id)
        preset = self._transcripts.get(video.video_id)
        if preset is not None:
            return preset
        # A default ASR transcript: one segment of plausible, parameterized production speech.
        return RawTranscript(
            video_id=video.video_id,
            caption_source=CaptionSource.ASR,
            language="en",
            fetched_via="faster-whisper-fake",
            segments=[TranscriptSegment(start_s=0.0, duration_s=6.0, text=self._default_text)],
        )
