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
