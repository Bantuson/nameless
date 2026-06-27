"""SynthesisPipeline — end-to-end select -> synthesize -> GATE -> emit -> store, all on fakes (KNOW-07/08/09).

Proves the full Phase-5 flow works with no API/DB: the fixtures' P1 cells are authored as gated draft
skills, the conflict cell preserves both camps, and a synthesizer that fabricates a number is REJECTED by
the gate (the model gets no special pass).
"""

from __future__ import annotations

from knowledge_pipeline.adapters import FakeSkillSynthesizer, InMemorySkillStore
from knowledge_pipeline.domain.skills import ProductionCell, SkillStatus
from knowledge_pipeline.pure.cell_selection import clusters_for_cell
from knowledge_pipeline.pure.synthesis_template import template_synthesize
from knowledge_pipeline.synthesis_pipeline import SynthesisPipeline

from .conftest import FIXED_NOW, mine_fixture_claim_layer


def test_authors_the_p1_cells_as_draft_skills(synthesis_plane):
    pipeline, store, _claims, _corpus = synthesis_plane
    report = pipeline.synthesize()
    assert report.rejected == 0
    assert report.authored == report.total_cells == 5
    slugs = {s.slug for s in store.list_skills()}
    assert slugs == {
        "rnb-vocal-layering", "amapiano-drums", "amapiano-bassline",
        "deep-house-bassline", "rnb-bassline",
    }
    assert all(s.status is SkillStatus.DRAFT for s in store.list_skills())


def test_north_star_cells_authored_first(synthesis_plane):
    pipeline, _store, _claims, _corpus = synthesis_plane
    report = pipeline.synthesize()
    authored = [o.cell for o in report.outcomes if o.status == "authored"]
    assert authored[0] == "rnb-vocal-layering"
    assert authored[1] == "amapiano-drums"


def test_conflict_cell_is_authored_and_flagged_contested(synthesis_plane):
    pipeline, store, _claims, _corpus = synthesis_plane
    pipeline.synthesize()
    skill = store.get_skill(next(s.id for s in store.list_skills() if s.slug == "amapiano-drums"))
    assert skill.default_contested is True
    assert skill.conflict_topics == 1
    assert "[flex-synth]" in skill.body_md and "[layered-samples]" in skill.body_md


def test_resynthesis_is_idempotent(synthesis_plane):
    pipeline, store, _claims, _corpus = synthesis_plane
    pipeline.synthesize()
    n1 = store.stats().total_skills
    pipeline.synthesize()
    assert store.stats().total_skills == n1  # upsert by cell id, no duplicates


def test_a_synthesizer_that_invents_a_number_is_rejected_by_the_gate():
    # Wire a MALICIOUS synthesizer that injects a fabricated parameter into the default body. The pipeline's
    # gate must REJECT it — the synthesizer (real or fake) gets no special pass.
    claim_store, corpus, _snaps = mine_fixture_claim_layer()
    clusters = claim_store.list_clusters()

    class InventingSynth:
        def synthesize(self, cell, cluster_seq):
            draft = template_synthesize(cell, list(cluster_seq))
            poisoned = draft.default.model_copy(update={"body": draft.default.body + " Boost 999 Hz heavily."})
            return draft.model_copy(update={"default": poisoned})

    store = InMemorySkillStore()
    pipeline = SynthesisPipeline(InventingSynth(), store, claim_store, corpus=corpus, now=lambda: FIXED_NOW)
    report = pipeline.synthesize()

    assert report.rejected == report.total_cells       # every cell's poisoned default is caught
    assert report.authored == 0
    assert store.stats().total_skills == 0             # nothing untraceable shipped
    assert any("invented_number" in "; ".join(o.reasons) for o in report.outcomes)


def test_all_evidenced_cells_authored_when_p1_only_disabled(synthesis_plane):
    pipeline, store, _claims, _corpus = synthesis_plane
    pipeline._config.p1_only = False  # author every evidenced cell
    report = pipeline.synthesize()
    # the fixtures only evidence P1 cells, so the count matches, but the path is exercised
    assert report.authored >= 5
