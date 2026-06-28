"""FakeStemSeparator tests — deterministic, named stems with separator provenance (no demucs)."""

from __future__ import annotations

from nameless_workers.adapters.stem_separator_fake import FakeStemSeparator
from nameless_workers.domain.separation import HTDEMUCS_4, HTDEMUCS_6, StemType

TRACK_A = b"finished song A: amapiano, warm, late-night" * 8
TRACK_B = b"finished song B: deep house, bright" * 8


def test_default_produces_the_four_htdemucs_stems_with_provenance():
    result = FakeStemSeparator().separate(TRACK_A)
    assert result.stem_types() == list(HTDEMUCS_4)
    assert result.separator_model == "fake-demucs"
    assert result.separator_version == "0"
    assert result.sample_rate == 44_100
    # Each stem carries non-empty bytes.
    assert all(len(s.audio) > 0 for s in result.stems)


def test_six_stem_variant_isolates_piano_and_guitar():
    sep = FakeStemSeparator(stem_types=HTDEMUCS_6, model="fake-demucs_6s", version="0")
    result = sep.separate(TRACK_A)
    assert result.stem_types() == list(HTDEMUCS_6)
    assert StemType.PIANO in result.stem_types()
    assert StemType.GUITAR in result.stem_types()
    assert result.separator_model == "fake-demucs_6s"


def test_separation_is_deterministic_per_input():
    sep = FakeStemSeparator()
    a1 = sep.separate(TRACK_A)
    a2 = sep.separate(TRACK_A)
    assert a1 == a2
    # Different track → different stem bytes.
    b = sep.separate(TRACK_B)
    assert [s.audio for s in b.stems] != [s.audio for s in a1.stems]


def test_stems_within_a_track_are_distinct():
    result = FakeStemSeparator().separate(TRACK_A)
    blobs = [s.audio for s in result.stems]
    # No two stems of the same track are byte-identical (so their content hashes differ).
    assert len(set(blobs)) == len(blobs)
