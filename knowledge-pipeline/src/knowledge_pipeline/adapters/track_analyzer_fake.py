"""FakeTrackAnalyzer — the deterministic, ML-free :class:`~knowledge_pipeline.ports.TrackAnalyzer`.

Stands in for the real workers feature/CLAP pipeline with ZERO torch/librosa/CLAP and ZERO audio bytes:
it returns pre-computed :class:`~knowledge_pipeline.domain.grounding.AudioAnalysisRecord`s keyed by
``track_id`` (loaded from the bundled audio-feature fixtures, or supplied directly by a test). That is what
lets the entire Phase-6 grounding flow — decompose -> gather parents -> analyze tracks -> synthesize ->
GATE -> emit — run on the base env, exercising the real control flow with only the audio leaf swapped.

It records ``calls`` so a test can assert which tracks were analyzed, mirroring the Phase-2/3/4 fakes.
"""

from __future__ import annotations

from typing import Mapping

from ..domain.grounding import AudioAnalysisRecord, TrackRef


class FakeTrackAnalyzer:
    """A deterministic stand-in for the real workers-backed analyzer; canned records by ``track_id``."""

    def __init__(self, records: Mapping[str, AudioAnalysisRecord]) -> None:
        self._records = dict(records)
        self.calls: list[str] = []

    def analyze(self, track: TrackRef) -> AudioAnalysisRecord:
        self.calls.append(track.track_id)
        rec = self._records.get(track.track_id)
        if rec is None:
            raise KeyError(
                f"no canned analysis record for track '{track.track_id}'. "
                "Add a fixture under fixtures/grounding/tracks/ or pass it to FakeTrackAnalyzer."
            )
        return rec
