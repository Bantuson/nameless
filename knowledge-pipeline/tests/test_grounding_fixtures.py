"""Phase-6 fixtures + fake analyzer — the offline inputs for the grounding flow (KNOW-10)."""

from __future__ import annotations

import pytest

from knowledge_pipeline.adapters import FakeTrackAnalyzer
from knowledge_pipeline.domain.grounding import TrackRef
from knowledge_pipeline.grounding_fixtures import load_audio_records, load_grounding_fixtures


def test_loads_the_artist_roster_records():
    records, tracks = load_audio_records()
    assert set(records) == {"ben_produces_emoyeni", "liyana_ricky_sunday_blue", "lowbass_djy_lounge"}
    artists = {r.artist for r in records.values()}
    assert artists == {"Ben Produces", "Liyana Ricky", "Lowbass Djy"}
    # the records measure surface only (sane musical ranges), and converge in the alt-piano band
    assert all(106 <= r.tempo_bpm <= 116 for r in records.values())
    assert all("min" in r.key_name for r in records.values())
    assert {t.track_id for t in tracks} == set(records)


def test_parent_corpus_includes_the_decomposition_parents_and_reused_conflict():
    fx = load_grounding_fixtures()
    # the three Phase-6 parent tutorials
    assert {"amapiano_groove_tut", "jazzy_piano_tut", "deephouse_space_tut"} <= set(fx.parents.transcripts)
    # the reused bundled amapiano log-drum conflict
    assert {"amapiano_logdrum_flex", "amapiano_logdrum_layered"} <= set(fx.parents.transcripts)


def test_fake_analyzer_serves_canned_records_and_records_calls():
    records, _tracks = load_audio_records()
    analyzer = FakeTrackAnalyzer(records)
    rec = analyzer.analyze(TrackRef(track_id="ben_produces_emoyeni", artist="Ben Produces"))
    assert rec.citation_id == "audio:ben-produces-emoyeni"
    assert analyzer.calls == ["ben_produces_emoyeni"]


def test_fake_analyzer_raises_on_an_unknown_track():
    analyzer = FakeTrackAnalyzer({})
    with pytest.raises(KeyError):
        analyzer.analyze(TrackRef(track_id="nope", artist="?"))
