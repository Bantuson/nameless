"""Grounding-fixture loader — the offline inputs for the Phase-6 sparse-genre flow (KNOW-10).

One small place that knows the two Phase-6 fixture shapes, used by BOTH the test suite and the CLI's
offline ``skills ground --fixtures`` demo:

  * **Parent tutorial claims** (``fixtures/grounding/parents/*.json``) — the claim-fixture schema reused
    verbatim from Phase 4 (:func:`knowledge_pipeline.claim_fixtures.load_claim_fixtures`). These are the
    cited, taught claims for the decomposition's PARENT cells (amapiano groove, jazzy piano, deep-house
    space). The loader also folds in the BUNDLED Phase-4 claim fixtures (``fixtures/claims/``) so the
    already-authored amapiano log-drum FLEX-vs-layered *conflict* is reused as parent evidence — the
    grounding pipeline filters both down to the decomposition's parent cells.

  * **Audio analysis records** (``fixtures/grounding/tracks/*.json``) — canned, deterministic
    :class:`~knowledge_pipeline.domain.grounding.AudioAnalysisRecord`s for the artist roster (Ben Produces,
    Liyana Ricky, Lowbass Djy), exactly what the env-gated real :class:`TrackAnalyzer` would emit. The fake
    analyzer serves these by ``track_id``, so the whole flow runs with no torch/CLAP and no audio bytes.

Keeping these as data files (not Python literals) means the audio "signatures" are reviewable and the
roster is editable without touching code — the same discipline as the Phase-3/4 transcript/claim fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .claim_fixtures import (
    DEFAULT_CLAIM_FIXTURE_DIR,
    ClaimFixtureCorpus,
    load_claim_fixtures,
)
from .domain.grounding import AudioAnalysisRecord, ClapTag, TrackRef

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "grounding"
DEFAULT_PARENTS_DIR = _FIXTURE_ROOT / "parents"
DEFAULT_TRACKS_DIR = _FIXTURE_ROOT / "tracks"


@dataclass
class GroundingFixtures:
    """The offline inputs the Phase-6 grounding flow needs."""

    parents: ClaimFixtureCorpus = field(default_factory=ClaimFixtureCorpus)
    records: dict[str, AudioAnalysisRecord] = field(default_factory=dict)
    tracks: list[TrackRef] = field(default_factory=list)


def _merge_corpora(a: ClaimFixtureCorpus, b: ClaimFixtureCorpus) -> ClaimFixtureCorpus:
    """Union two claim-fixture corpora (b's entries win on a video-id clash). Pure-ish (no I/O)."""
    out = ClaimFixtureCorpus()
    out.transcripts = {**a.transcripts, **b.transcripts}
    out.scripted = {**a.scripted, **b.scripted}
    out.genres = {**a.genres, **b.genres}
    return out


def _record_from_dict(data: dict) -> AudioAnalysisRecord:
    region = data.get("region_ms", [0, 0])
    return AudioAnalysisRecord(
        track_id=data["track_id"],
        artist=data["artist"],
        title=data.get("title", ""),
        genre=data.get("genre", "alt-piano"),
        source_track_id=data.get("source_track_id"),
        region_ms=(int(region[0]), int(region[1])),
        tempo_bpm=float(data.get("tempo_bpm", 0.0)),
        swing_ratio=float(data.get("swing_ratio", 0.0)),
        key_name=data.get("key_name", ""),
        key_confidence=float(data.get("key_confidence", 0.0)),
        tonal_balance={k: float(v) for k, v in data.get("tonal_balance", {}).items()},
        stereo_width=float(data.get("stereo_width", 0.0)),
        loudness_lufs=float(data.get("loudness_lufs", 0.0)),
        clap_tags=[ClapTag(tag=t["tag"], score=float(t["score"])) for t in data.get("clap_tags", [])],
        analyzer_version=data.get("analyzer_version", "fake-grounding-fixture-0"),
        embed_model=data.get("embed_model", "fake-clap-0"),
        separator_model=data.get("separator_model"),
    )


def load_audio_records(
    directory: str | Path = DEFAULT_TRACKS_DIR,
) -> tuple[dict[str, AudioAnalysisRecord], list[TrackRef]]:
    """Load every track fixture into ``(records_by_id, track_refs)``. Deterministic."""
    directory = Path(directory)
    records: dict[str, AudioAnalysisRecord] = {}
    tracks: list[TrackRef] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = _record_from_dict(data)
        records[rec.track_id] = rec
        tracks.append(
            TrackRef(
                track_id=rec.track_id,
                artist=rec.artist,
                title=rec.title,
                genre=rec.genre,
                source_track_id=rec.source_track_id,
                audio_uri=data.get("audio_uri"),
            )
        )
    return records, tracks


def load_grounding_fixtures(
    *,
    parents_dir: str | Path = DEFAULT_PARENTS_DIR,
    tracks_dir: str | Path = DEFAULT_TRACKS_DIR,
    include_bundled_claims: bool = True,
) -> GroundingFixtures:
    """Load the parent claim corpus + the canned audio records for the offline grounding flow.

    Args:
        parents_dir: directory of Phase-6 parent claim fixtures.
        tracks_dir: directory of Phase-6 audio-record fixtures.
        include_bundled_claims: also fold in the bundled Phase-4 claim fixtures (so the reused amapiano
            log-drum conflict becomes parent evidence). The pipeline filters to the decomposition's parents.
    """
    parents = load_claim_fixtures(parents_dir)
    if include_bundled_claims:
        parents = _merge_corpora(load_claim_fixtures(DEFAULT_CLAIM_FIXTURE_DIR), parents)
    records, tracks = load_audio_records(tracks_dir)
    return GroundingFixtures(parents=parents, records=records, tracks=tracks)
