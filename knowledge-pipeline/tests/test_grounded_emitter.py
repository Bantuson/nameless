"""Phase-6 grounded emitter — LOW-confidence SKILL.md with the decomposition + audio provenance (KNOW-10)."""

from __future__ import annotations

from knowledge_pipeline.domain.grounding import AudioAnalysisRecord, ClapTag
from knowledge_pipeline.domain.skills import SkillStatus
from knowledge_pipeline.pure.audio_claims import audio_derived_claims
from knowledge_pipeline.pure.confidence import grounding_note
from knowledge_pipeline.pure.decompose import ALT_PIANO_TARGET, decompose
from knowledge_pipeline.pure.grounded_emitter import emit_grounded_skill_md

from .conftest import make_draft


def _record() -> AudioAnalysisRecord:
    return AudioAnalysisRecord(
        track_id="ben_produces_emoyeni", artist="Ben Produces", title="Emoyeni", genre="alt-piano",
        region_ms=(0, 30000), tempo_bpm=110.0, swing_ratio=0.16, key_name="F:min", key_confidence=0.62,
        tonal_balance={"low": 0.34, "mid": 0.41, "high": 0.25}, stereo_width=0.18, loudness_lufs=-9.5,
        clap_tags=[ClapTag(tag="amapiano", score=0.41)], analyzer_version="fake-0", embed_model="fake-clap-0",
    )


def _grounded_md() -> str:
    rec = _record()
    claims = [a.to_claim() for a in audio_derived_claims(rec)]
    draft = make_draft([claims[0]], cell=ALT_PIANO_TARGET)  # default on the measured tempo
    decomp = decompose(ALT_PIANO_TARGET)
    note = grounding_note(decomp, audio_track_count=1, confidence="LOW")
    return emit_grounded_skill_md(draft, decomp, [rec], confidence="LOW", grounding_note=note)


def test_frontmatter_is_low_and_flagged_grounded():
    md = _grounded_md()
    assert "confidence: LOW" in md
    assert "grounded: true" in md
    assert "name: alternative-piano-composite" in md  # the draft name (cell slug) rides through


def test_body_shows_the_decomposition_and_negative_space():
    md = _grounded_md()
    assert "## Grounding — how this skill was derived" in md
    assert "amapiano log-drum groove" in md
    assert "jazzy / soulful extended piano voicings" in md
    assert "deep-house space and dub" in md
    assert "Negative space" in md


def test_body_names_the_audio_records_as_citations():
    md = _grounded_md()
    assert "audio:ben-produces-emoyeni" in md
    assert "Ben Produces" in md


def test_body_carries_the_honest_not_direct_tutorials_note():
    low = _grounded_md().lower()
    assert "not direct tutorials" in low
    assert "measured surface only" in low or "audio measures surface" in low


def test_keeps_the_layered_sections():
    md = _grounded_md()
    for header in ("## Default — act on this", "## Consensus", "## Contested", "## Citations"):
        assert header in md


def test_promoted_status_swaps_only_the_banner():
    rec = _record()
    claims = [a.to_claim() for a in audio_derived_claims(rec)]
    draft = make_draft([claims[0]], cell=ALT_PIANO_TARGET)
    md = emit_grounded_skill_md(draft, decompose(ALT_PIANO_TARGET), [rec], status=SkillStatus.PROMOTED)
    assert "status: promoted" in md
    assert "confidence: LOW" in md  # promotion never changes the honest LOW stamp
