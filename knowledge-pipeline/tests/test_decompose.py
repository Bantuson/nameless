"""Phase-6 decomposition — the parent-technique map for alt-piano (KNOW-10, PITFALLS #4)."""

from __future__ import annotations

import pytest

from knowledge_pipeline.domain.skills import ProductionCell
from knowledge_pipeline.pure.decompose import (
    ALT_PIANO_TARGET,
    decompose,
    has_decomposition,
    known_targets,
)


def test_alt_piano_target_lands_at_a_composite_path():
    assert ALT_PIANO_TARGET.genre == "alternative-piano"
    assert ALT_PIANO_TARGET.stage == "composite"
    assert ALT_PIANO_TARGET.relpath == "skills/production/composite/alternative-piano/SKILL.md"


def test_decomposes_into_the_three_named_parents():
    # FEATURES: alt-piano = amapiano-groove + jazzy-piano + deep-house-space.
    decomp = decompose(ALT_PIANO_TARGET)
    parent_cells = {(p.cell.stage, p.cell.genre) for p in decomp.parents}
    assert parent_cells == {
        ("drums", "amapiano"),       # log-drum groove
        ("chords", "rnb"),           # jazzy / soulful extended voicings
        ("atmosphere", "deep-house"),  # space / dub
    }
    assert decomp.parent_count == 3


def test_captures_the_negative_space():
    # PITFALLS #4: the identity is in what the subgenre OMITS vs its parents, not their sum.
    decomp = decompose(ALT_PIANO_TARGET)
    assert decomp.negative_space, "negative space must be captured, not reconstructed as parent-sum"
    blob = " ".join(decomp.negative_space).lower()
    assert "sparser" in blob or "space" in blob
    assert "slower" in blob or "soulful" in blob


def test_every_parent_is_a_distinct_authorable_cell():
    decomp = decompose(ALT_PIANO_TARGET)
    cells = decomp.parent_cells()
    assert len(cells) == len({c.slug for c in cells})  # no duplicate parents
    assert all(isinstance(c, ProductionCell) for c in cells)


def test_unknown_target_is_a_hard_failure_not_a_guess():
    # We never auto-guess a decomposition; an unknown target raises rather than fabricating parents.
    assert not has_decomposition(ProductionCell(stage="drums", genre="gqom"))
    with pytest.raises(KeyError):
        decompose(ProductionCell(stage="drums", genre="gqom"))


def test_alt_piano_is_a_known_target():
    assert any(t.slug == ALT_PIANO_TARGET.slug for t in known_targets())
