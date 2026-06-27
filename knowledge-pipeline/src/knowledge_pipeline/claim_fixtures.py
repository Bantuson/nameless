"""Claim-fixture loader — turns ``fixtures/claims/*.json`` into fake-adapter inputs (Phase-4 offline path).

One small place that knows the claim-fixture schema, used by BOTH the test suite and the CLI's offline
``claims mine --fixtures`` demo. Each file pairs a transcript with the claims a faithful extractor would
emit from it::

    {
      "transcript": {"video_id": "...", "caption_source": "manual", "genre": ["amapiano"],
                     "segments": [{"start_s": 12.0, "duration_s": 5.0, "text": "..."}]},
      "claims": [{"segment": 0, "claim_text": "...", "technique": "log-drum-sound-source",
                  "stage": "drums", "genre": ["amapiano"], "stance": "flex-synth", "confidence": 0.8}]
    }

Each claim references a segment by INDEX; the loader pulls that segment's verbatim text as the claim's
``quote`` and its start as ``timestamp_ms`` — so the scripted claims are genuinely citation-anchored and
:func:`verify_citation` passes. ``load_claim_fixtures`` returns the three structures the offline path
needs: the per-video :class:`RawTranscript` map (the snapshot source), the scripted
``video_id -> [Claim]`` map (for :class:`FakeClaimExtractor`), and the per-video discovery genres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .domain.claims import Claim
from .domain.models import CaptionSource, RawTranscript, TranscriptSegment

DEFAULT_CLAIM_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "claims"


@dataclass
class ClaimFixtureCorpus:
    """The fake-adapter inputs derived from a directory of claim-fixture files."""

    transcripts: dict[str, RawTranscript] = field(default_factory=dict)
    scripted: dict[str, list[Claim]] = field(default_factory=dict)
    genres: dict[str, list[str]] = field(default_factory=dict)

    @property
    def video_ids(self) -> list[str]:
        return list(self.transcripts.keys())


def _transcript(data: dict) -> RawTranscript:
    segs = [
        TranscriptSegment(
            start_s=float(s["start_s"]),
            duration_s=(float(s["duration_s"]) if s.get("duration_s") is not None else None),
            text=s["text"],
        )
        for s in data.get("segments", [])
    ]
    return RawTranscript(
        video_id=data["video_id"],
        caption_source=CaptionSource(data.get("caption_source", "manual")),
        language=data.get("language", "en"),
        fetched_via="claim-fixture",
        segments=segs,
    )


def _claims(data: dict, transcript: RawTranscript, default_genres: list[str]) -> list[Claim]:
    out: list[Claim] = []
    for raw in data.get("claims", []):
        seg_idx = int(raw["segment"])
        seg = transcript.segments[seg_idx]
        out.append(
            Claim(
                claim_text=raw["claim_text"],
                technique=raw["technique"],
                stage=raw["stage"],
                genre=raw.get("genre", default_genres),
                stance=raw.get("stance"),
                confidence=float(raw.get("confidence", 0.6)),
                source_video_id=transcript.video_id,
                timestamp_ms=int(round(seg.start_s * 1000)),
                quote=seg.text,  # verbatim => citation verifies
                caption_source=transcript.caption_source,
            )
        )
    return out


def load_claim_fixtures(directory: str | Path = DEFAULT_CLAIM_FIXTURE_DIR) -> ClaimFixtureCorpus:
    """Load every ``*.json`` claim fixture in ``directory`` into the fake-adapter input structures."""
    directory = Path(directory)
    corpus = ClaimFixtureCorpus()
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        t = data["transcript"]
        transcript = _transcript(t)
        genres = list(t.get("genre", []))
        corpus.transcripts[transcript.video_id] = transcript
        corpus.genres[transcript.video_id] = genres
        corpus.scripted[transcript.video_id] = _claims(data, transcript, genres)
    return corpus
