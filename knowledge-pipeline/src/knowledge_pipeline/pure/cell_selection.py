"""``select_cells`` / ``clusters_for_cell`` — PURE P1 north-star cell ordering (KNOW-09).

Phase 5 authors one SKILL.md per ``(stage, genre)`` cell, but NOT every cell and not in arbitrary order:
the project's whole bet is "quality in, quality out" starts with *what you choose to author first*. So
this module turns the available Phase-4 clusters into the set of authorable cells and orders them by the
north-star priority (FEATURES.md "the P1 cells cluster around exactly the north-star fusion"):

  1. the signature cells (``NORTH_STAR_ORDER``) — R&B vocal-layering/adlibs/lush-chords/atmosphere,
     amapiano + alt-piano log-drum groove + jazzy piano, deep-house space/groove — author ABSOLUTE first;
  2. the rest of the P1 grid;
  3. everything else (non-P1) last (and droppable with ``p1_only=True``).

All deterministic, no I/O. A cell is *authorable* only if real clusters exist for it — we never invent a
cell with no evidence. ``clusters_for_cell`` is the inverse: the clusters whose stage matches and whose
genre union contains the cell's genre (a cross-genre consensus like the sub-bass high-pass surfaces in
every genre it was evidenced for — corroboration is shared, not fragmented).
"""

from __future__ import annotations

from typing import Sequence

from ..domain.claims import ClaimCluster
from ..domain.skills import NORTH_STAR_ORDER, P1_CELLS, ProductionCell

# rank bands: north-star signature < other P1 < non-P1 (lower sorts earlier)
_NORTH_STAR_RANK = {cell: i for i, cell in enumerate(NORTH_STAR_ORDER)}
_P1_BAND = len(NORTH_STAR_ORDER) + 100
_OTHER_BAND = _P1_BAND + 100


def is_p1(stage: str, genre: str) -> bool:
    """True iff ``(stage, genre)`` is a P1 cell in the FEATURES grid. Pure."""
    return (stage, genre) in P1_CELLS


def cell_priority(stage: str, genre: str) -> int:
    """The authoring-priority rank for a cell (lower = author earlier). Pure.

    North-star signature cells keep their explicit ``NORTH_STAR_ORDER`` index; other P1 cells share one
    band above them; non-P1 cells share the lowest band. Ties inside a band are broken by ``(genre, stage)``
    alphabetically at the call site, so the full order is fully deterministic.
    """
    key = (stage, genre)
    if key in _NORTH_STAR_RANK:
        return _NORTH_STAR_RANK[key]
    if key in P1_CELLS:
        return _P1_BAND
    return _OTHER_BAND


def clusters_for_cell(clusters: Sequence[ClaimCluster], cell: ProductionCell) -> list[ClaimCluster]:
    """The clusters that belong to ``cell``: same stage, and the cell's genre in the cluster's genres. Pure.

    Sorted deterministically (contested last, then by topic) so a cell's skill is reproducible. Contested
    topics sort after consensus so the emitted skill reads consensus-then-contested.
    """
    out = [
        cl
        for cl in clusters
        if cl.stage == cell.stage and cell.genre in (cl.genre or [])
    ]
    out.sort(key=lambda cl: (cl.is_contested, cl.topic))
    return out


def candidate_cells(clusters: Sequence[ClaimCluster]) -> set[ProductionCell]:
    """Every ``(stage, genre)`` cell that has at least one cluster of evidence. Pure."""
    cells: set[ProductionCell] = set()
    for cl in clusters:
        for g in cl.genre or []:
            cells.add(ProductionCell(stage=cl.stage, genre=g))
    return cells


def select_cells(clusters: Sequence[ClaimCluster], *, p1_only: bool = True) -> list[ProductionCell]:
    """Authorable cells ordered north-star-first (KNOW-09). Pure.

    Args:
        clusters: the cross-referenced Phase-4 clusters (the available evidence).
        p1_only: when True (default) keep only P1 grid cells — author the north-star cluster, decompose /
            defer the rest (FEATURES). When False, every evidenced cell is returned (non-P1 last).

    Returns:
        Deterministically-ordered cells: north-star signature first, then the rest of P1, then non-P1.
    """
    cells = candidate_cells(clusters)
    if p1_only:
        cells = {c for c in cells if is_p1(c.stage, c.genre)}
    return sorted(cells, key=lambda c: (cell_priority(c.stage, c.genre), c.genre, c.stage))
