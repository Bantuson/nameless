"""template_synthesize — the deterministic layered synthesizer + the synthesis-ONLY-over-claims invariant.

The defining Phase-5 discipline (KNOW-07): the synthesizer decides a default ON TOP of the evidence but may
introduce NOTHING not already in the claim set. These tests pin that — every number and every citation in
the produced draft must trace back to the input clusters — plus the default-selection heuristic and the
both-camps-preserved conflict behaviour.
"""

from __future__ import annotations

import pytest

from knowledge_pipeline.domain.keys import numbers
from knowledge_pipeline.domain.skills import ProductionCell, SectionKind
from knowledge_pipeline.pure.cell_selection import clusters_for_cell
from knowledge_pipeline.pure.synthesis_template import template_synthesize

from .conftest import mine_fixture_claim_layer


def _layer():
    store, _corpus, _snaps = mine_fixture_claim_layer()
    return store.list_clusters(), {c.id: c for c in store.list_claims()}


def _cell_clusters(stage, genre):
    clusters, _claims = _layer()
    return clusters_for_cell(clusters, ProductionCell(stage=stage, genre=genre))


# ---- the invariant -----------------------------------------------------------------------------


def test_every_number_in_the_draft_comes_from_a_cited_claim():
    clusters, _claims = _layer()
    for cell in (
        ProductionCell(stage="bassline", genre="deep-house"),
        ProductionCell(stage="drums", genre="amapiano"),
        ProductionCell(stage="vocal-layering", genre="rnb"),
    ):
        cc = clusters_for_cell(clusters, cell)
        draft = template_synthesize(cell, cc)
        # the universe of numbers the input evidence contains (claim quotes)
        evidence_numbers: set[str] = set()
        for cl in cc:
            for c in cl.consensus + cl.conflicts:
                evidence_numbers |= numbers(c.quote)
        draft_numbers: set[str] = set()
        for s in draft.all_sections():
            draft_numbers |= numbers(s.body)
        assert draft_numbers <= evidence_numbers, f"{cell.slug} introduced numbers not in any claim"


def test_every_citation_is_a_real_input_claim():
    clusters, _claims = _layer()
    cell = ProductionCell(stage="bassline", genre="deep-house")
    cc = clusters_for_cell(clusters, cell)
    input_ids = {c.id for cl in cc for c in (cl.consensus + cl.conflicts)}
    draft = template_synthesize(cell, cc)
    assert draft.cited_claim_ids <= input_ids
    assert draft.cited_claim_ids  # and it actually cites something


def test_section_bodies_are_verbatim_claim_text():
    # the template never paraphrases — each non-empty section body contains a real claim_text span.
    cc = _cell_clusters("drums", "amapiano")
    draft = template_synthesize(ProductionCell(stage="drums", genre="amapiano"), cc)
    claim_texts = {c.claim_text.strip() for cl in cc for c in (cl.consensus + cl.conflicts)}
    for s in draft.all_sections():
        assert s.body == "" or any(piece in s.body for piece in claim_texts)


# ---- default-selection heuristic ---------------------------------------------------------------


def test_default_rests_on_the_best_corroborated_topic():
    # deep-house bassline has sub-bass-highpass (3 sources) and sub-bass-mono (1) -> default = highpass.
    cell = ProductionCell(stage="bassline", genre="deep-house")
    draft = template_synthesize(cell, _cell_clusters("bassline", "deep-house"))
    assert draft.default.technique == "sub-bass-highpass"
    assert draft.default.distinct_sources == 3
    assert draft.default.stance is None  # uncontested default


def test_contested_default_picks_a_camp_and_flags_it():
    cell = ProductionCell(stage="drums", genre="amapiano")
    draft = template_synthesize(cell, _cell_clusters("drums", "amapiano"))
    assert draft.default.stance is not None          # the default takes a side …
    assert draft.conflict_sections()                 # … and BOTH camps are still preserved
    stances = {s.stance for s in draft.conflict_sections()}
    assert stances == {"flex-synth", "layered-samples"}
    assert draft.default.stance in stances


def test_consensus_and_conflict_sections_are_partitioned_by_topic():
    cell = ProductionCell(stage="bassline", genre="deep-house")
    draft = template_synthesize(cell, _cell_clusters("bassline", "deep-house"))
    assert all(s.kind is SectionKind.CONSENSUS for s in draft.consensus_sections())
    assert draft.conflict_sections() == []           # this cell is uncontested
    assert {s.technique for s in draft.consensus_sections()} == {"sub-bass-highpass", "sub-bass-mono"}


def test_distinct_sources_counts_corroboration_not_repeats():
    cell = ProductionCell(stage="bassline", genre="deep-house")
    draft = template_synthesize(cell, _cell_clusters("bassline", "deep-house"))
    hp = next(s for s in draft.consensus_sections() if s.technique == "sub-bass-highpass")
    assert hp.distinct_sources == 3                  # deephouse + rnb + amapiano


def test_empty_clusters_raises_rather_than_inventing():
    with pytest.raises(ValueError):
        template_synthesize(ProductionCell(stage="mastering", genre="rnb"), [])
