"""Phase-5 domain + keys.numbers — the typed boundary the gate/emitter/store rely on (KNOW-07/08/09)."""

from __future__ import annotations

from knowledge_pipeline.domain.keys import numbers
from knowledge_pipeline.domain.skills import (
    ProductionCell,
    SkillStatus,
    compute_skill_id,
    confidence_tier,
)


def test_numbers_extracts_and_canonicalizes():
    assert numbers("High-pass around 30 Hz, mono below 120 Hz") == {"30", "120"}
    assert numbers("layer a kick an 808 and a marimba") == {"808"}
    assert numbers("no parameters here") == set()
    # canonicalization: leading zeros + trailing .0 fold so 030 == 30 == 30.0
    assert numbers("030 and 30.0") == {"30"}
    # magnitude only — the unit ("hz") travels in the prose, not the numeric token
    assert numbers("300hz") == {"300"}


def test_numbers_are_sign_aware():
    # WR-01: a leading minus is captured and preserved, so boost (+6) and cut (-6) do NOT collapse.
    assert numbers("boost 6 dB") == {"6"}
    assert numbers("cut -6 dB") == {"-6"}
    assert numbers("boost 6 dB") != numbers("cut -6 dB")
    # -0 has no negative magnitude; leading zeros still fold under the sign
    assert numbers("-030") == {"-30"}
    assert numbers("-0 dB") == {"0"}
    # a hyphen that is a CONNECTOR, not a sign, is not read as negative (drum-machine names, sub-bass labels)
    assert numbers("layer a TR-808 and the sub-808") == {"808"}


def test_invented_number_sign_flip_is_rejected():
    # WR-01 end-to-end: a "+6 dB" assertion grounded ONLY by a "-6 dB" quote must REJECT (boost != cut).
    from .conftest import make_claim, make_draft
    from knowledge_pipeline.pure.citation_gate import RejectionCode, citation_gate

    claim = make_claim(claim_text="Cut the mud at 400 Hz by -6 dB.", quote="cut the mud at 400 hz by -6 db",
                       technique="eq-cut", stage="mixdown", video="mx", ts_ms=5000)
    claims = {claim.id: claim}
    # same craft words, but the sign is flipped: +6 (boost) where the only evidence says -6 (cut).
    draft = make_draft([claim], default_body="Cut the mud at 400 Hz by +6 dB.")
    result = citation_gate(draft, claims)
    assert result.ok is False
    assert RejectionCode.INVENTED_NUMBER.value in result.codes
    assert any("6" in r.detail for r in result.rejections)


def test_production_cell_slug_and_relpath():
    cell = ProductionCell(stage="vocal-layering", genre="rnb")
    assert cell.slug == "rnb-vocal-layering"
    assert cell.relpath == "skills/production/vocal-layering/rnb/SKILL.md"


def test_skill_id_is_deterministic_and_cell_addressed():
    a = compute_skill_id("drums", "amapiano")
    b = compute_skill_id("drums", "amapiano")
    assert a == b and a.startswith("skl_")
    assert compute_skill_id("bassline", "amapiano") != a  # different cell -> different id


def test_confidence_tier_bands():
    assert confidence_tier(3, contested=False) == "HIGH"
    assert confidence_tier(2, contested=False) == "MED"
    assert confidence_tier(1, contested=False) == "LOW"
    assert confidence_tier(5, contested=True) == "LOW"  # contested is always soft guidance


def test_status_enum_values():
    assert SkillStatus.DRAFT.value == "draft"
    assert SkillStatus.PROMOTED.value == "promoted"
