"""Phase-6 audio grounding — features->record mapping + measured claims cited to a record (KNOW-10)."""

from __future__ import annotations

from knowledge_pipeline.domain.grounding import (
    AudioAnalysisRecord,
    ClapTag,
    TrackRef,
    audio_snapshot,
)
from knowledge_pipeline.domain.keys import numbers
from knowledge_pipeline.pure.audio_claims import audio_derived_claims, features_to_record
from knowledge_pipeline.pure.citation import verify_citation


def _record(**over) -> AudioAnalysisRecord:
    base = dict(
        track_id="ben_produces_emoyeni",
        artist="Ben Produces",
        title="Emoyeni",
        genre="alt-piano",
        region_ms=(0, 30000),
        tempo_bpm=110.0,
        swing_ratio=0.16,
        key_name="F:min",
        key_confidence=0.62,
        tonal_balance={"low": 0.34, "mid": 0.41, "high": 0.25},
        stereo_width=0.18,
        loudness_lufs=-9.5,
        clap_tags=[ClapTag(tag="amapiano", score=0.41), ClapTag(tag="deep house", score=0.33)],
        analyzer_version="fake-0",
        embed_model="fake-clap-0",
    )
    base.update(over)
    return AudioAnalysisRecord(**base)


def test_features_to_record_is_a_pure_dto_mapping():
    track = TrackRef(track_id="t1", artist="A", title="T", genre="alt-piano")
    rec = features_to_record(
        track,
        tempo_bpm=110.0, swing_ratio=0.16, key_name="F:min", key_confidence=0.62,
        tonal_balance={"low": 0.34, "mid": 0.41, "high": 0.25}, stereo_width=0.18,
        loudness_lufs=-9.5, clap_tags=[ClapTag(tag="amapiano", score=0.4)],
        analyzer_version="v", embed_model="m",
    )
    assert rec.track_id == "t1" and rec.artist == "A"
    assert rec.tempo_bpm == 110.0 and rec.key_name == "F:min"
    assert rec.citation_id == "audio:t1"


def test_citation_id_is_audio_prefixed():
    assert _record().citation_id == "audio:ben-produces-emoyeni"


def test_audio_claims_are_measured_and_cited_to_the_record():
    rec = _record()
    claims = audio_derived_claims(rec)
    measures = {c.measure for c in claims}
    # exactly the surface audio measures well — and nothing else
    assert measures == {"tempo", "swing", "key-tendency", "tonal-balance", "stereo-width", "clap-vibe"}
    # every claim is cited to THIS record (the track is the citation)
    assert all(c.record_id == rec.citation_id for c in claims)
    assert all(c.artist == "Ben Produces" for c in claims)


def test_no_melodic_or_structural_claim_is_emitted():
    # PITFALLS #5/#6: audio measures SURFACE, never melody/chords/structure/intent.
    rec = _record()
    blob = " ".join(c.statement.lower() for c in audio_derived_claims(rec))
    for forbidden in ("melody", "chord progression", "structure", "lyrics", "emotional", "intent"):
        assert forbidden not in blob


def test_measured_numbers_live_verbatim_in_the_statement():
    # The tempo / swing / tonal-balance numbers must be present in the statement so the gate can prove them.
    rec = _record(tempo_bpm=110.0, swing_ratio=0.16)
    by_measure = {c.measure: c for c in audio_derived_claims(rec)}
    assert "110" in numbers(by_measure["tempo"].statement)
    assert "16" in numbers(by_measure["swing"].statement)          # 0.16 -> "16 percent"
    # tonal balance as integer percents
    assert {"34", "41", "25"} <= numbers(by_measure["tonal-balance"].statement)


def test_key_tendency_asserts_no_numeric_pitch_class():
    # The key CENTRE is prose only ("F:min", "minor") — no numeric pitch class that could read as craft.
    rec = _record(key_name="F:min")
    key_claim = next(c for c in audio_derived_claims(rec) if c.measure == "key-tendency")
    assert numbers(key_claim.statement) == set()
    assert "minor" in key_claim.statement.lower()


def test_clap_vibe_is_labelled_coarse_and_carries_no_scores():
    rec = _record()
    vibe = next(c for c in audio_derived_claims(rec) if c.measure == "clap-vibe")
    assert "coarse" in vibe.statement.lower()
    assert numbers(vibe.statement) == set()  # no scores asserted as craft numbers


def test_to_claim_round_trips_and_self_verifies_against_the_audio_snapshot():
    rec = _record()
    adcs = audio_derived_claims(rec)
    snap = audio_snapshot(rec, adcs)
    # the synthetic snapshot is keyed by the record's citation id, with one segment per measured claim
    assert snap.video_id == rec.citation_id
    assert len(snap.segments) == len(adcs)
    # each lifted Phase-4 claim verifies against that snapshot (the audio citation is auditable)
    for adc in adcs:
        claim = adc.to_claim()
        assert claim.source_video_id == rec.citation_id
        assert claim.quote == adc.statement
        chk = verify_citation(claim, snap)
        assert chk.ok, f"{adc.measure} did not verify: {chk.reason}"


def test_absent_measures_are_skipped_not_asserted_as_zero():
    # A record with no clap tags / no swing simply omits those claims (never asserts a fabricated 0).
    rec = _record(clap_tags=[], swing_ratio=0.0)
    measures = {c.measure for c in audio_derived_claims(rec)}
    assert "clap-vibe" not in measures
    assert "swing" not in measures
    assert "tempo" in measures  # the present measures still emit
