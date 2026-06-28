"""``grounding_confidence`` — PURE, honest confidence for a decomposition-grounded skill (KNOW-10).

This is the heart of the phase's honesty discipline. A normal authored skill earns HIGH/MED/LOW from how
many DISTINCT tutorial sources back its default (:func:`knowledge_pipeline.domain.skills.confidence_tier`).
A *sparse-genre* skill has (almost) NO direct tutorials — it is composed from parent techniques and
corroborated against measured audio. The temptation is to let the parents' or the audio's source count
inflate it to HIGH; that would present thin, indirect evidence as settled craft — the exact failure the
project exists to avoid (PITFALLS #4: "hold sparse-genre skills at lower confidence and label them as
such").

So the rule is deliberately blunt and conservative:

  * **The grounded path is LOW, always.** Grounded by decomposition + audio analysis is real evidence,
    but it is *indirect* and *thin*; it is never settled craft. This is the KNOW-10 invariant, and it is a
    tested one. It is also the SINGLE source of truth: :attr:`knowledge_pipeline.domain.skills.AuthoredSkill.confidence_tier`
    independently forces ``LOW`` for any ``grounded`` skill, so the label inside the emitted SKILL.md
    frontmatter and the label the registry/CLI report can never disagree (WR-01). A genre with enough
    direct tutorials to read higher should be authored on the NORMAL path, not grounded here.

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
        ``"LOW"`` — always, for the grounded path. Decomposition + audio is thin, indirect evidence and is
        never settled craft, and this MUST agree with
        :attr:`knowledge_pipeline.domain.skills.AuthoredSkill.confidence_tier` (which hard-forces ``LOW`` for
        any grounded skill). A separate ``MED`` ceiling here was the single source of a latent divergence
        between the emitted frontmatter and the registry (WR-01); it is removed. The ``direct_tutorial_sources``,
        ``parent_techniques`` and ``audio_track_count`` arguments are retained for the honest receipts in
        :func:`grounding_note` and for callers that still report them, but they cannot lift the tier.
    """
    # The KNOW-10 invariant, now unconditional: grounded ⇒ thin, indirect evidence ⇒ LOW. This is the one
    # source of truth for a grounded skill's confidence; the registry (confidence_tier) agrees by forcing
    # LOW for grounded too, so the file the agent loads and the CLI/registry never disagree (WR-01).
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
