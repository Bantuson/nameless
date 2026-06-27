"""Fixture-corpus loader — turns the on-disk ``fixtures/transcripts/*.json`` into fake-adapter inputs.

One small place that knows the fixture JSON schema, used by BOTH the test suite and the CLI's offline
``--fixtures`` demo path. A fixture file describes one video plus the captions a fetch would find and the
ASR a transcriber would produce::

    {
      "video":    {"video_id": "...", "title": "...", "channel": "...", "duration_s": 640,
                   "genre": "amapiano", "stage": "drums"},
      "captions": {"has_manual": true, "has_auto": false, "auto_quality": null,
                   "caption_source": "manual", "language": "en",
                   "segments": [{"start_s": 8.0, "duration_s": 4.0, "text": "..."}]},
      "asr":      {"language": "en", "segments": [{"start_s": 0.0, "text": "..."}]}   // optional
    }

``load_fixture_corpus`` returns the three structures the fakes consume: the list of :class:`VideoRef`,
the per-video :class:`CaptionFetch` map (for :class:`FixtureTranscriptFetcher`), and the per-video ASR
:class:`RawTranscript` map (for :class:`FixedTextTranscriber`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .domain.models import (
    CaptionAvailability,
    CaptionFetch,
    CaptionSource,
    RawTranscript,
    TranscriptSegment,
    VideoRef,
)

# The repo's bundled fixture corpus (knowledge-pipeline/fixtures/transcripts/).
DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "transcripts"


@dataclass
class FixtureCorpus:
    """The three fake-adapter inputs derived from a directory of fixture files."""

    videos: list[VideoRef]
    fetches: dict[str, CaptionFetch]
    asr: dict[str, RawTranscript]


def _segments(raw: list[dict]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start_s=float(s["start_s"]),
            duration_s=(float(s["duration_s"]) if s.get("duration_s") is not None else None),
            text=s["text"],
        )
        for s in raw
    ]


def _load_one(path: Path) -> tuple[VideoRef, CaptionFetch, Optional[RawTranscript]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    v = data["video"]
    video = VideoRef(
        video_id=v["video_id"],
        title=v.get("title", ""),
        channel=v.get("channel"),
        duration_s=v.get("duration_s"),
        genre=v.get("genre"),
        stage=v.get("stage"),
        artist_anchor=v.get("artist_anchor"),
    )

    caps = data.get("captions", {})
    cap_source = CaptionSource(caps.get("caption_source", "none"))
    cap_segments = _segments(caps.get("segments", []))
    transcript = (
        RawTranscript(
            video_id=video.video_id,
            caption_source=cap_source,
            language=caps.get("language", "en"),
            fetched_via="fixture",
            segments=cap_segments,
        )
        if cap_segments and cap_source is not CaptionSource.NONE
        else None
    )
    fetch = CaptionFetch(
        video_id=video.video_id,
        availability=CaptionAvailability(
            has_manual=bool(caps.get("has_manual", False)),
            has_auto=bool(caps.get("has_auto", False)),
            auto_quality=caps.get("auto_quality"),
        ),
        transcript=transcript,
    )

    asr_data = data.get("asr")
    asr_transcript = (
        RawTranscript(
            video_id=video.video_id,
            caption_source=CaptionSource.ASR,
            language=asr_data.get("language", "en"),
            fetched_via="fixture-asr",
            segments=_segments(asr_data.get("segments", [])),
        )
        if asr_data
        else None
    )
    return video, fetch, asr_transcript


def load_fixture_corpus(directory: str | Path = DEFAULT_FIXTURE_DIR) -> FixtureCorpus:
    """Load every ``*.json`` fixture in ``directory`` into the fake-adapter input structures."""
    directory = Path(directory)
    videos: list[VideoRef] = []
    fetches: dict[str, CaptionFetch] = {}
    asr: dict[str, RawTranscript] = {}
    for path in sorted(directory.glob("*.json")):
        video, fetch, asr_transcript = _load_one(path)
        videos.append(video)
        fetches[video.video_id] = fetch
        if asr_transcript is not None:
            asr[video.video_id] = asr_transcript
    return FixtureCorpus(videos=videos, fetches=fetches, asr=asr)
