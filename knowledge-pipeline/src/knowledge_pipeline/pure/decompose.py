"""``decompose`` — PURE parent-technique decomposition for under-tutorialized targets (KNOW-10).

When a cell has (almost) no direct tutorials, the only honest move is to reconstruct it from PARENT
techniques that *are* taught and grounded (FEATURES "parent-technique decomposition"; PITFALLS #4). This
module holds that mapping as reviewable DATA (the decomposition is an editorial hypothesis, kept next to
the types like the genres/skills grids) plus the one pure function that returns it.

The flagship target is **alternative piano** (the private-school / soulful-piano amapiano lane —
Ben Produces, Liyana Ricky, Lowbass Djy), decomposed into the three parents the research names
(FEATURES "alt-piano = amapiano-groove + jazzy-piano + deep-house-space"):

  * amapiano **log-drum groove**        (drums, amapiano)      — the rhythmic foundation, softer here
  * jazzy / soulful **piano voicings**  (chords, rnb)          — extended, space-leaving harmony
  * deep-house **space / dub**          (atmosphere, deep-house) — air, delay sends, panned percussion

…and, crucially, its NEGATIVE SPACE — what the subgenre deliberately omits/breaks versus those parents
(PITFALLS #4: "the genre's identity is in what the parents omit or break, not their sum"). Decomposition
only *proposes* the blend; the Phase-6 audio-analysis leg *disposes* (measures it against real tracks).
"""

from __future__ import annotations

from ..domain.grounding import DecompositionMap, ParentTechnique
from ..domain.skills import ProductionCell

# The composite cell the alternative-piano skill is authored at. "composite" is an explicit pseudo-stage:
# the skill spans groove + harmony + space rather than one stage, so it lands at
# skills/production/composite/alternative-piano/SKILL.md (FEATURES: "or a composite").
ALT_PIANO_TARGET = ProductionCell(stage="composite", genre="alternative-piano")


# The decomposition table — editorial DATA (reviewable), keyed by the target cell's slug. Each parent is an
# already-authorable (stage, genre) cell whose Phase-4/5 claims compose the target; the negative space is
# what alt-piano subtracts from / subverts in those parents (its real identity).
_DECOMPOSITIONS: dict[str, DecompositionMap] = {
    ALT_PIANO_TARGET.slug: DecompositionMap(
        target=ALT_PIANO_TARGET,
        parents=[
            ParentTechnique(
                cell=ProductionCell(stage="drums", genre="amapiano"),
                label="amapiano log-drum groove",
                contributes="the rhythmic foundation — the log drum and its swing — but softer and rounder, "
                "carrying momentum without dominating the mix.",
            ),
            ParentTechnique(
                cell=ProductionCell(stage="chords", genre="rnb"),
                label="jazzy / soulful extended piano voicings",
                contributes="the harmonic identity — lush, extended (7th/9th) voicings that leave space for "
                "each element, the private-school discipline.",
            ),
            ParentTechnique(
                cell=ProductionCell(stage="atmosphere", genre="deep-house"),
                label="deep-house space and dub",
                contributes="the air around the parts — delay/dub sends, airy pads and panned organic "
                "percussion that open up the arrangement.",
            ),
        ],
        negative_space=[
            "Sparser than mainstream amapiano: space is left for each instrument and the vocal — "
            "'less nightclub, more sophisticated lounge'.",
            "Slower and more soulful than club deep house — a relaxed lane, not a peak-time pump.",
            "The log drum is present but deliberately softer/rounder than mainstream amapiano; "
            "it is not the loudest element.",
        ],
        rationale="Alternative piano is under-tutorialized, so it is composed from its taught parents and "
        "cross-checked against measured signatures of real tracks — never fabricated. Decomposition "
        "proposes the blend; audio analysis disposes.",
    ),
}


def decompose(target: ProductionCell) -> DecompositionMap:
    """Return the parent-technique decomposition for ``target``. Pure.

    Args:
        target: the under-tutorialized composite cell to ground (e.g. :data:`ALT_PIANO_TARGET`).

    Returns:
        The reviewed :class:`DecompositionMap` (parents + negative space).

    Raises:
        KeyError: if there is no decomposition authored for the target (we never *guess* a decomposition;
            an unknown target is a deliberate failure, not a fabricated parent list).
    """
    try:
        return _DECOMPOSITIONS[target.slug]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"no decomposition authored for cell '{target.slug}'. Add one to decompose._DECOMPOSITIONS "
            "(decomposition is an editorial hypothesis, never auto-guessed)."
        ) from exc


def has_decomposition(target: ProductionCell) -> bool:
    """True iff a reviewed decomposition exists for ``target``. Pure."""
    return target.slug in _DECOMPOSITIONS


def known_targets() -> list[ProductionCell]:
    """Every target a decomposition is authored for (for the CLI / discoverability). Pure."""
    return [m.target for m in _DECOMPOSITIONS.values()]
