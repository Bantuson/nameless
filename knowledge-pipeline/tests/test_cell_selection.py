"""cell_selection — P1 north-star ordering over the available clusters (KNOW-09)."""

from __future__ import annotations

from knowledge_pipeline.domain.skills import ProductionCell
from knowledge_pipeline.pure.cell_selection import (
    candidate_cells,
    cell_priority,
    clusters_for_cell,
    is_p1,
    select_cells,
)

from .conftest import mine_fixture_claim_layer


def _clusters():
    store, _corpus, _snaps = mine_fixture_claim_layer()
    return store.list_clusters()


def test_p1_membership_matches_the_features_grid():
    assert is_p1("vocal-layering", "rnb")        # the Sonder/Brent Faiyaz signature
    assert is_p1("drums", "amapiano")            # the log drum (groove engine)
    assert is_p1("bassline", "deep-house")
    assert not is_p1("mastering", "alt-piano")   # an explicit "—" cell in the grid
    assert not is_p1("melody", "amapiano")       # a P2 cell


def test_candidate_cells_only_come_from_real_clusters():
    cells = candidate_cells(_clusters())
    # the fixtures evidence exactly these (stage, genre) cells — nothing invented.
    assert ProductionCell(stage="drums", genre="amapiano") in cells
    assert ProductionCell(stage="vocal-layering", genre="rnb") in cells
    assert ProductionCell(stage="bassline", genre="deep-house") in cells
    # a cross-genre consensus (sub-bass high-pass) surfaces in every genre it was evidenced for
    assert ProductionCell(stage="bassline", genre="rnb") in cells
    assert ProductionCell(stage="bassline", genre="amapiano") in cells


def test_select_cells_orders_north_star_signature_first():
    order = [(c.stage, c.genre) for c in select_cells(_clusters(), p1_only=True)]
    # vocal-layering/rnb (rank 0) and drums/amapiano (the log drum) lead the bassline cells.
    assert order[0] == ("vocal-layering", "rnb")
    assert order[1] == ("drums", "amapiano")
    assert order.index(("drums", "amapiano")) < order.index(("bassline", "deep-house"))


def test_select_cells_is_deterministic():
    a = select_cells(_clusters(), p1_only=True)
    b = select_cells(_clusters(), p1_only=True)
    assert [c.slug for c in a] == [c.slug for c in b]


def test_p1_only_drops_non_p1_cells():
    p1 = {(c.stage, c.genre) for c in select_cells(_clusters(), p1_only=True)}
    allc = {(c.stage, c.genre) for c in select_cells(_clusters(), p1_only=False)}
    assert p1 <= allc
    assert all(is_p1(s, g) for (s, g) in p1)


def test_clusters_for_cell_filters_by_stage_and_genre():
    clusters = _clusters()
    cell = ProductionCell(stage="drums", genre="amapiano")
    cell_clusters = clusters_for_cell(clusters, cell)
    assert len(cell_clusters) == 1
    assert cell_clusters[0].topic == "drums/log-drum-sound-source"
    assert cell_clusters[0].is_contested  # the FLEX-vs-layered conflict


def test_clusters_for_cell_sorts_consensus_before_contested():
    # synthesize a cell with both kinds: deep-house bassline (2 consensus topics, no conflict here)
    clusters = clusters_for_cell(_clusters(), ProductionCell(stage="bassline", genre="deep-house"))
    assert [cl.is_contested for cl in clusters] == sorted(cl.is_contested for cl in clusters)


def test_priority_bands_rank_north_star_below_p1_below_other():
    assert cell_priority("vocal-layering", "rnb") < cell_priority("beats", "rnb")  # north-star < other P1
    assert cell_priority("beats", "rnb") < cell_priority("mastering", "alt-piano")  # P1 < non-P1
