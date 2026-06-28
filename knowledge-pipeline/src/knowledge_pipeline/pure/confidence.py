"""``grounding_confidence`` — PURE, honest confidence for a decomposition-grounded skill (KNOW-10).

This is the heart of the phase's honesty discipline. A normal authored skill earns HIGH/MED/LOW from how
many DISTINCT tutorial sources back its default (:func:`knowledge_pipeline.domain.skills.confidence_tier`).
A *sparse-genre* skill has (almost) NO direct tutorials — it is composed from parent techniques and
corroborated against measured audio. The temptation is to let the parents' or the audio's source count
inflate it to HIGH; that would present thin, indirect evidence as settled craft — the exact failure the
project exists to avoid (PITFALLS #4: "hold sparse-genre skills at lower confidence and label them as
such").

So the rule is deliberately blunt and conservative:

  * **No direct tutorials -> LOW, always.** Grounded by decomposition + audio analysis is real evidence,
    but it is *indirect* and *thin*; it is never settled craft. This is the KNOW-10 invariant, and it is a
    tested one.
  * Some direct tutorials could lift it, but even then the sparsity discount keeps it at most MED — a
    sparse genre never reads HIGH off a decomposition.

The companion :func:`grounding_note` produces the explicit prose stamp that rides in the skill's
frontmatter and body: "grounded by decomposition + audio analysis, NOT direct tutorials." Confidence is a
tier PLUS the receipts behind it — never a bare number, and here never an overstatement.
"""

from __future__ import annotations

from ..domain.grounding import DecompositionMap

# Confidence tiers (mirror domain.skills.confidence_tier's vocabulary).
LOW = "LOW"
MED = "MED"
HIGH = "HIGH"


def grounding_confidence(
    *,
    direct_tutorial_sources: int,
    parent_techniques: int,
    audio_track_count: int,
) -> str:
    """The honest tier for a decomposition+audio-grounded skill. Pure (KNOW-10).

    Args:
        direct_tutorial_sources: distinct tutorial sources that teach the TARGET subgenre directly
            (≈0 for alternative piano — that is the whole reason for this phase).
        parent_techniques: how many parent cells the target decomposes into (breadth of the hypothesis).
        audio_track_count: how many real tracks were analyzed and corroborate the signature.

    Returns:
        ``"LOW"`` whenever there are no direct tutorials (the sparse-genre case) — grounded-by-decomposition
        is never settled craft. With some direct tutorials AND broad corroboration it may reach ``"MED"``,
        but a sparse genre never reads ``"HIGH"`` off a decomposition.
    """
    if direct_tutorial_sources <= 0:
        # The KNOW-10 invariant: decomposition + audio only ⇒ thin, indirect evidence ⇒ LOW.
        return LOW
    # Indirectly supported but with SOME direct grounding: a discounted ceiling of MED.
    if direct_tutorial_sources >= 3 and parent_techniques >= 2 and audio_track_count >= 3:
        return MED
    return LOW


def is_low_by_construction(direct_tutorial_sources: int) -> bool:
    """True iff this skill MUST be LOW because it has no direct tutorials (the KNOW-10 floor). Pure."""
    return direct_tutorial_sources <= 0


def grounding_note(
    decomposition: DecompositionMap,
    *,
    audio_track_count: int,
    confidence: str = LOW,
) -> str:
    """The explicit honesty stamp for the skill frontmatter/body (KNOW-10). Pure.

    States plainly that the skill is grounded by decomposition + audio analysis, NOT direct tutorials, names
    the parents and the number of corroborating tracks, and flags the CLAP-coarseness caveat — so neither
    the agent nor the user can mistake thin grounding for taught, settled craft.
    """
    parents = ", ".join(p.label for p in decomposition.parents)
    return (
        f"{confidence} confidence — grounded by parent-technique decomposition + audio analysis of "
        f"{audio_track_count} released track(s), NOT direct tutorials. Composed from parents ({parents}) "
        "and cross-checked against measured (non-melodic) signatures of real tracks. Treat as soft "
        "guidance: the subgenre is under-tutorialized, and CLAP genre tags are coarse — audio measures "
        "surface, not intent."
    )
