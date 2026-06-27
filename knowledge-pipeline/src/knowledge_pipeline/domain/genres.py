"""The north-star discovery grid — the genres, production stages, and artist/producer anchors.

These constants define the *target* of KNOW-01: the production-stage x north-star-genre grid plus the
artist-anchored searches. They are data, not logic — :func:`knowledge_pipeline.pure.query_grid.query_grid`
turns them into concrete search queries. Keeping them here (typed, in one place) means the grid is
reviewable and the "what are we even looking for" decision is explicit, not buried in a loop.

The north-star sound (CLAUDE.md): Sonder / Brent Faiyaz vocal layering + atmosphere, fused across
R&B x amapiano x deep house x alternative piano. The grid is intentionally concentrated on that fusion
rather than "all of music production" — quality in, quality out starts with *what you choose to ingest*.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------------------------
# Axis 1 — the north-star fusion genres (the columns of the grid)
# ---------------------------------------------------------------------------------------------
# Canonical genre labels used everywhere downstream (registry rows, --by-genre grouping, Phase-4
# claim schema). Keep these stable: changing a label re-buckets the whole corpus.
GENRES: tuple[str, ...] = (
    "rnb",              # R&B — Sonder / Brent Faiyaz lineage (vocal layering + atmosphere)
    "amapiano",         # log-drum groove, shakers, spacious arrangement
    "deep-house",       # rolling sub, pads, hypnotic space
    "alt-piano",        # alternative piano (amapiano subgenre) — UNDER-tutorialized (sparse-genre, Phase 6)
)

# Human-facing search synonyms per genre — what producers actually *say* on YouTube. The grid expands
# each genre into these so discovery is not hostage to one phrasing ("rnb" vs "r&b" vs "rhythm and blues").
GENRE_SEARCH_TERMS: dict[str, tuple[str, ...]] = {
    "rnb": ("rnb", "r&b", "rnb soul"),
    "amapiano": ("amapiano", "amapiano log drum", "private school amapiano"),
    "deep-house": ("deep house", "soulful deep house"),
    "alt-piano": ("alternative piano amapiano", "alt piano amapiano", "piano amapiano"),
}

# ---------------------------------------------------------------------------------------------
# Axis 2 — the production stages (the rows of the grid)
# ---------------------------------------------------------------------------------------------
# The "logical production stack of skill" axis: every cell is (genre x stage), e.g. (amapiano x drums).
# This is the same stage taxonomy the Phase-4 claim schema and the Phase-5 SKILL.md tree are organized by,
# so discovery, claims, and skills all share one spine.
STAGES: tuple[str, ...] = (
    "beats",
    "drums",            # incl. the amapiano log drum
    "bassline",
    "chords",           # incl. alt-piano voicings
    "melody",
    "vocals",
    "vocal-layering",   # the Sonder/Brent Faiyaz signature — first-class stage
    "arrangement",
    "mixing",
    "mastering",
    "atmosphere",       # space, reverb, texture — the "vibe" stage
)

# Human-facing search phrasing per stage (appended to a genre term + "tutorial").
STAGE_SEARCH_TERMS: dict[str, tuple[str, ...]] = {
    "beats": ("beat making",),
    "drums": ("drums", "drum pattern", "log drum"),
    "bassline": ("bassline", "bass"),
    "chords": ("chords", "chord progression"),
    "melody": ("melody",),
    "vocals": ("vocals", "vocal recording"),
    "vocal-layering": ("vocal layering", "vocal stacking", "vocal harmonies"),
    "arrangement": ("arrangement", "song structure"),
    "mixing": ("mixing", "mixdown"),
    "mastering": ("mastering",),
    "atmosphere": ("atmosphere", "ambience", "reverb space"),
}


# ---------------------------------------------------------------------------------------------
# Axis 3 — artist / producer anchors (named-source searches)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ArtistAnchor:
    """A named artist/producer to anchor discovery on, with the genre cell they ground.

    ``alt-piano`` is deliberately anchored on Ben Produces / Liyana Ricky / Lowbass Djy because that
    subgenre is under-tutorialized (PITFALLS Pitfall 4): the grid alone will not surface it, so we name
    the people who actually make it. These anchors are *also* the artists whose released tracks the
    Phase-6 audio-grounding leg analyzes when tutorials run thin.
    """

    name: str
    genre: str  # the GENRES label this anchor primarily grounds


ARTIST_ANCHORS: tuple[ArtistAnchor, ...] = (
    # R&B north-star (vibe / vocal layering reference)
    ArtistAnchor("Sonder", "rnb"),
    ArtistAnchor("Brent Faiyaz", "rnb"),
    # Amapiano / alternative-piano producers (the sparse-genre anchors)
    ArtistAnchor("Ben Produces", "alt-piano"),
    ArtistAnchor("Liyana Ricky", "alt-piano"),
    ArtistAnchor("Lowbass Djy", "amapiano"),
)
