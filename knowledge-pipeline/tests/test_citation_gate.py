"""citation_gate — the hard Phase-5 reject gate (KNOW-08). A grounded draft PASSES; every failure REJECTS.

This is the make-or-break test: it proves the gate catches each GIGO failure mode as its own auditable
reject — invented numbers, uncited assertions, citations to non-existent sources, tampered quotes,
hallucinated craft, and citation rot — while letting a faithful, fully-grounded draft through.
"""

from __future__ import annotations

from knowledge_pipeline.domain.models import CaptionSource, RawTranscript, TranscriptSegment
from knowledge_pipeline.domain.skills import SectionKind, SkillCitation, SkillSection
from knowledge_pipeline.pure.citation_gate import RejectionCode, citation_gate

from .conftest import make_cell, make_citation, make_claim, make_draft, make_section


def _snap_from(claim) -> RawTranscript:
    """A snapshot whose segment IS the claim's quote at its timestamp (so verify_citation passes)."""
    return RawTranscript(
        video_id=claim.source_video_id,
        caption_source=CaptionSource.MANUAL,
        segments=[TranscriptSegment(start_s=claim.timestamp_ms / 1000.0, duration_s=5.0, text=claim.quote)],
    )


# ---- PASS --------------------------------------------------------------------------------------


def test_grounded_draft_passes_the_gate():
    claim = make_claim(
        claim_text="High-pass the sub bass around 30 Hz to keep the low end tight.",
        quote="High-pass the sub bass around 30 Hz to keep the low end tight.",
        technique="sub-bass-highpass", stage="bassline", video="dh", ts_ms=8000,
    )
    claims = {claim.id: claim}
    draft = make_draft([claim], sections=[make_section([claim])])
    result = citation_gate(draft, claims, snapshots={claim.source_video_id: _snap_from(claim)})
    assert result.ok is True
    assert result.rejections == ()


def test_pass_holds_when_every_number_is_in_a_cited_quote():
    # body asserts 30 AND 120 — both present across the cited quotes -> grounded.
    c1 = make_claim(claim_text="High-pass the sub around 30 Hz.", quote="High-pass the sub around 30 hz.",
                    technique="sub-bass-highpass", stage="bassline", video="a", ts_ms=1000)
    c2 = make_claim(claim_text="Keep the sub in mono below 120 Hz.", quote="Keep the sub in mono below 120 hz.",
                    technique="sub-bass-highpass", stage="bassline", video="b", ts_ms=2000)
    claims = {c1.id: c1, c2.id: c2}
    draft = make_draft([c1, c2], default_body="High-pass the sub around 30 Hz. Keep the sub in mono below 120 Hz.")
    assert citation_gate(draft, claims).ok is True


# ---- REJECT: invented number (the headline check) ----------------------------------------------


def test_invented_number_is_rejected():
    claim = make_claim(claim_text="High-pass the sub bass around 30 Hz.",
                       quote="High-pass the sub bass around 30 hz.", video="dh", ts_ms=8000)
    claims = {claim.id: claim}
    # the default asserts 40 Hz — a confident value present in NO cited quote.
    draft = make_draft([claim], default_body="High-pass the sub bass around 40 Hz.")
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.INVENTED_NUMBER.value in result.codes
    assert any("40" in r.detail for r in result.rejections)


def test_a_number_present_in_the_cited_quote_is_allowed():
    claim = make_claim(claim_text="Saturate the log drum with an 808 layer.",
                       quote="Saturate the log drum with an 808 layer.", video="am", ts_ms=3000,
                       technique="log-drum", stage="drums")
    claims = {claim.id: claim}
    draft = make_draft([claim], default_body="Saturate the log drum with an 808 layer.")
    assert citation_gate(claims=claims, draft=draft).ok is True


# ---- REJECT: uncited assertion -----------------------------------------------------------------


def test_uncited_section_is_rejected():
    claim = make_claim(video="dh", ts_ms=8000)
    claims = {claim.id: claim}
    uncited = SkillSection(
        kind=SectionKind.CONSENSUS, topic="bassline/sub-bass-highpass", technique="sub-bass-highpass",
        stage="bassline", genre=["deep-house"], body="High-pass the sub somewhere down low.", citations=[],
    )
    draft = make_draft([claim], sections=[uncited])
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.UNCITED.value in result.codes


# ---- REJECT: citation to a non-existent source -------------------------------------------------


def test_citation_to_nonexistent_claim_is_rejected():
    real = make_claim(video="dh", ts_ms=8000)
    claims = {real.id: real}
    ghost = SkillSection(
        kind=SectionKind.CONSENSUS, topic="bassline/sub-bass-highpass", technique="sub-bass-highpass",
        stage="bassline", genre=["deep-house"], body="High-pass the sub bass around 30 hz.",
        citations=[SkillCitation(claim_id="clm_ghost", source_video_id="dh", timestamp_ms=8000,
                                 quote="High-pass the sub bass around 30 hz.")],
    )
    draft = make_draft([real], sections=[ghost])
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.NONEXISTENT_SOURCE.value in result.codes


def test_tampered_citation_quote_is_rejected():
    claim = make_claim(claim_text="High-pass the sub bass around 30 Hz.",
                       quote="High-pass the sub bass around 30 hz.", video="dh", ts_ms=8000)
    claims = {claim.id: claim}
    tampered = SkillSection(
        kind=SectionKind.CONSENSUS, topic=claim.topic, technique=claim.technique, stage=claim.stage,
        genre=["deep-house"], body="High-pass the sub bass around 30 Hz.",
        citations=[SkillCitation(claim_id=claim.id, source_video_id="dh", timestamp_ms=8000,
                                 quote="Add a tasteful reverb to the master bus.")],  # not the real quote
    )
    draft = make_draft([claim], sections=[tampered])
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.QUOTE_TAMPERED.value in result.codes


# ---- REJECT: hallucinated craft (numberless) ---------------------------------------------------


def test_ungrounded_hallucinated_assertion_is_rejected():
    claim = make_claim(claim_text="High-pass the sub bass around 30 Hz.",
                       quote="High-pass the sub bass around 30 hz.", video="dh", ts_ms=8000)
    claims = {claim.id: claim}
    # prose the cited claim does not support at all — no number to catch, but nothing grounds it either.
    draft = make_draft([claim], default_body="Paint the mixdown a vivid purple and sprinkle fairy dust.")
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.UNGROUNDED_ASSERTION.value in result.codes


# ---- REJECT: citation rot (reuses verify_citation) ---------------------------------------------


def test_citation_rot_is_rejected_against_the_snapshot():
    claim = make_claim(claim_text="High-pass the sub bass around 30 Hz.",
                       quote="High-pass the sub bass around 30 hz.", video="dh", ts_ms=8000)
    claims = {claim.id: claim}
    draft = make_draft([claim])
    # the snapshot no longer contains the quote (a re-captioned / taken-down source) -> not_found.
    rotted = RawTranscript(
        video_id="dh", caption_source=CaptionSource.AUTO,
        segments=[TranscriptSegment(start_s=8.0, duration_s=5.0, text="totally unrelated chatter here")],
    )
    result = citation_gate(draft, claims, snapshots={"dh": rotted})
    assert result.ok is False
    assert RejectionCode.CITATION_ROT.value in result.codes


def test_gate_reasons_are_human_readable():
    claim = make_claim(quote="High-pass the sub bass around 30 hz.", video="dh", ts_ms=8000)
    draft = make_draft([claim], default_body="High-pass at 40 Hz and 99 dB.")
    result = citation_gate(draft, {claim.id: claim})
    assert not result.ok
    # every reason is a "code: detail" string an auditor can read
    assert all(": " in reason for reason in result.reasons)
