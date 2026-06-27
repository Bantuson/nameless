"""``query_grid`` — turn the north-star (genre x stage) grid + artist anchors into search queries.

Pure function (KNOW-01): given the stages, genres, and artist anchors, produce the de-duplicated set of
:class:`DiscoveryQuery` the discovery source will run. No network, no I/O — just the combinatorics of
"what do we search for". That makes the discovery *target* unit-testable: you can assert the grid covers
every (genre x stage) cell and every anchor, without touching YouTube.

Design choices, all reviewable here:
  * Every grid query is ``"{genre-term} {stage-term} tutorial"`` — the word "tutorial" biases YouTube
    toward taught material over songs/mixes (the corpus is *tutorials*).
  * Genre + stage each expand through their synonym lists (``GENRE_SEARCH_TERMS`` / ``STAGE_SEARCH_TERMS``)
    so we are not hostage to one phrasing — but we cap to the FIRST synonym per axis by default to keep
    the query count sane (``expand_synonyms=True`` opens the full cross-product when you want max recall).
  * Artist anchors yield ``"{artist} {stage-term}"`` for a few high-value stages plus a bare
    ``"{artist} type beat breakdown"`` — how producers actually title homage/breakdown videos.

KNOW-04 math (why this can yield 100+): |genres| x |stages| grid queries + anchor queries, each fanned
out by the discovery source to N results, dedups to well over 100 candidate videos. See README.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from ..domain.genres import (
    ARTIST_ANCHORS,
    GENRE_SEARCH_TERMS,
    GENRES,
    STAGE_SEARCH_TERMS,
    STAGES,
    ArtistAnchor,
)
from ..domain.models import DiscoveryQuery

# Stages that make sense to pair with a named artist/producer anchor (a focused subset — searching
# "Sonder mastering tutorial" is noise; "Sonder vocal layering" / "Lowbass Djy log drum" is signal).
_ANCHOR_STAGES: tuple[str, ...] = ("drums", "bassline", "chords", "vocal-layering", "atmosphere")


def _genre_terms(genre: str, expand: bool) -> Sequence[str]:
    terms = GENRE_SEARCH_TERMS.get(genre, (genre,))
    return terms if expand else terms[:1]


def _stage_terms(stage: str, expand: bool) -> Sequence[str]:
    terms = STAGE_SEARCH_TERMS.get(stage, (stage,))
    return terms if expand else terms[:1]


def query_grid(
    stages: Iterable[str] = STAGES,
    genres: Iterable[str] = GENRES,
    artists: Iterable[ArtistAnchor] = ARTIST_ANCHORS,
    *,
    expand_synonyms: bool = False,
    tutorial_suffix: str = "tutorial",
) -> list[DiscoveryQuery]:
    """Build the de-duplicated discovery query set for the (genre x stage) grid + artist anchors.

    Args:
        stages / genres / artists: the axes (default to the full north-star grid).
        expand_synonyms: if True, cross-product ALL phrasing synonyms per axis (max recall, more
            queries); if False (default), use the first synonym per axis (lean, still covers every cell).
        tutorial_suffix: appended to every grid query to bias toward taught material.

    Returns:
        A list of unique :class:`DiscoveryQuery`, grid queries first (genre-major, stage-minor) then
        artist-anchor queries. Order is deterministic so a re-run produces the same plan.
    """
    genres = list(genres)
    stages = list(stages)
    artists = list(artists)

    seen: set[str] = set()
    out: list[DiscoveryQuery] = []

    def _add(q: DiscoveryQuery) -> None:
        key = q.text.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(q)

    # ---- grid: genre x stage ----
    for genre in genres:
        for stage in stages:
            for g_term in _genre_terms(genre, expand_synonyms):
                for s_term in _stage_terms(stage, expand_synonyms):
                    text = " ".join(p for p in (g_term, s_term, tutorial_suffix) if p).strip()
                    _add(
                        DiscoveryQuery(
                            text=text,
                            kind="grid",
                            genre=genre,
                            stage=stage,
                        )
                    )

    # ---- artist / producer anchors ----
    for anchor in artists:
        # a few focused stage searches per anchor
        for stage in _ANCHOR_STAGES:
            for s_term in _stage_terms(stage, expand_synonyms):
                _add(
                    DiscoveryQuery(
                        text=f"{anchor.name} {s_term}".strip(),
                        kind="artist",
                        genre=anchor.genre,
                        stage=stage,
                        artist_anchor=anchor.name,
                    )
                )
        # the homage / breakdown phrasing
        _add(
            DiscoveryQuery(
                text=f"{anchor.name} type beat breakdown",
                kind="artist",
                genre=anchor.genre,
                artist_anchor=anchor.name,
            )
        )

    return out


def grid_coverage(queries: Sequence[DiscoveryQuery]) -> dict[tuple[Optional[str], Optional[str]], int]:
    """How many queries hit each (genre, stage) cell — a pure helper to assert/inspect grid coverage."""
    cov: dict[tuple[Optional[str], Optional[str]], int] = {}
    for q in queries:
        if q.kind == "grid":
            cell = (q.genre, q.stage)
            cov[cell] = cov.get(cell, 0) + 1
    return cov
