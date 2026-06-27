"""query_grid tests (KNOW-01) — the discovery PLAN is correct + covers every north-star cell."""

from __future__ import annotations

from knowledge_pipeline.domain.genres import ARTIST_ANCHORS, GENRES, STAGES
from knowledge_pipeline.pure.query_grid import grid_coverage, query_grid


def test_grid_covers_every_genre_x_stage_cell():
    queries = query_grid()
    coverage = grid_coverage(queries)
    # Every (genre, stage) cell must be represented by at least one grid query.
    for genre in GENRES:
        for stage in STAGES:
            assert coverage.get((genre, stage), 0) >= 1, f"missing cell ({genre}, {stage})"


def test_every_grid_query_is_a_tutorial_query():
    queries = [q for q in query_grid() if q.kind == "grid"]
    assert queries
    assert all(q.text.endswith("tutorial") for q in queries)
    assert all(q.genre in GENRES and q.stage in STAGES for q in queries)


def test_artist_anchors_present_with_provenance():
    queries = query_grid()
    artist_queries = [q for q in queries if q.kind == "artist"]
    names = {q.artist_anchor for q in artist_queries}
    for anchor in ARTIST_ANCHORS:
        assert anchor.name in names
    # the homage phrasing exists for each anchor
    breakdowns = {q.text for q in artist_queries if "type beat breakdown" in q.text}
    assert len(breakdowns) == len(ARTIST_ANCHORS)


def test_queries_are_deduplicated_and_deterministic():
    a = query_grid()
    b = query_grid()
    texts = [q.text for q in a]
    assert texts == [q.text for q in b]          # deterministic order
    assert len(texts) == len(set(texts))          # no duplicate query strings


def test_count_supports_100_plus_target():
    # The default grid alone fans out to enough queries that, at a few results each, clears 100 videos.
    queries = query_grid()
    grid_q = [q for q in queries if q.kind == "grid"]
    assert len(grid_q) == len(GENRES) * len(STAGES)
    # 5 results/query * this many grid queries is comfortably > 100 candidate slots (KNOW-04 math).
    assert len(grid_q) * 5 >= 100


def test_expand_synonyms_increases_recall():
    lean = query_grid(expand_synonyms=False)
    wide = query_grid(expand_synonyms=True)
    assert len(wide) > len(lean)


def test_subset_axes_scope_the_grid():
    queries = query_grid(stages=["drums"], genres=["amapiano"], artists=[])
    assert all(q.genre == "amapiano" for q in queries)
    assert {q.stage for q in queries} == {"drums"}
    assert all(q.kind == "grid" for q in queries)
