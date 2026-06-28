"""Phase-6 confidence — honest LOW-by-construction for sparse-genre grounding (KNOW-10)."""

from __future__ import annotations

from knowledge_pipeline.pure.confidence import (
    grounding_confidence,
    grounding_note,
    is_low_by_construction,
)
from knowledge_pipeline.pure.decompose import ALT_PIANO_TARGET, decompose


def test_no_direct_tutorials_is_low_no_matter_how_much_audio_corroborates():
    # KNOW-10: grounded by decomposition + audio only ⇒ LOW, even with many corroborating tracks.
    assert grounding_confidence(direct_tutorial_sources=0, parent_techniques=3, audio_track_count=3) == "LOW"
    assert grounding_confidence(direct_tutorial_sources=0, parent_techniques=5, audio_track_count=10) == "LOW"
    assert is_low_by_construction(0)


def test_grounded_path_is_always_low_regardless_of_direct_tutorials():
    # WR-01: the grounded path is LOW unconditionally — the MED ceiling was a divergent second source of
    # truth vs AuthoredSkill.confidence_tier (which forces LOW for grounded). No argument can lift it.
    assert grounding_confidence(direct_tutorial_sources=3, parent_techniques=2, audio_track_count=3) == "LOW"
    assert grounding_confidence(direct_tutorial_sources=1, parent_techniques=3, audio_track_count=3) == "LOW"
    assert grounding_confidence(direct_tutorial_sources=99, parent_techniques=9, audio_track_count=99) == "LOW"
    # is_low_by_construction still reflects the "no direct tutorials" floor independently of the tier.
    assert not is_low_by_construction(3)


def test_grounding_note_states_decomposition_not_tutorials_and_names_parents():
    decomp = decompose(ALT_PIANO_TARGET)
    note = grounding_note(decomp, audio_track_count=3, confidence="LOW")
    low = note.lower()
    assert "low confidence" in low
    assert "not direct tutorials" in low
    assert "3 released track" in low
    # names the parents (so the honesty stamp is specific, not vague)
    assert "log-drum" in low and "piano" in low
    # the CLAP-coarseness caveat (PITFALLS #5) rides along
    assert "coarse" in low
