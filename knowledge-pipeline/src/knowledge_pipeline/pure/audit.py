"""``audit_sample`` / ``coverage`` — PURE human-spot-audit support (KNOW-11).

A solo build cannot eyeball every distilled claim, but it MUST eyeball *some* before trusting a skill to
the arranger/mixer agents — PITFALLS #3's cheap insurance against systemic distortion ("sample 10–20% of
distilled claims against their sources before a skill ships"). This module is the deterministic core of
that flow: it computes per-skill citation **coverage** + trust **flags**, and draws a reproducible
**sample** for review. The CLI's ``skills audit`` renders it; ``skills promote`` is the human action it
informs. Nothing here promotes anything — promotion stays a deliberate human gate.

All pure: coverage is arithmetic over the skill's stored roll-up; the sample uses an INJECTED
``random.Random`` (seeded) so "audit a sample of 2" is the same two skills every run — auditable, not
flaky.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

from ..domain.skills import AuthoredSkill, SkillStatus


@dataclass(frozen=True)
class SkillCoverage:
    """The audit verdict for one skill — coverage + confidence + the flags a human should look at."""

    skill_id: str
    slug: str
    status: str
    citation_count: int
    distinct_sources: int
    confidence_tier: str
    flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuditReport:
    """A sampled audit pass: the drawn sample's coverage rows + corpus-wide roll-up."""

    sampled: tuple[SkillCoverage, ...]
    total_skills: int
    draft: int
    promoted: int
    flagged: int
    sample_size: int


def coverage(skill: AuthoredSkill) -> SkillCoverage:
    """Compute one skill's coverage + trust flags. Pure.

    Flags surface exactly the things a human should not promote blind:
      * ``single-source-default`` — the opinionated default rests on one creator (LOW confidence).
      * ``contested-default``     — the default sits on a genuine disagreement (soft guidance).
      * ``uncited``               — no citations at all (a gate failure that must never reach here; flagged
                                    defensively so a bug can't silently ship an unsupported skill).
      * ``no-consensus``          — the cell has no corroborated topic (thin coverage).
    """
    flags: list[str] = []
    if skill.citation_count == 0:
        flags.append("uncited")
    if skill.default_contested:
        flags.append("contested-default")
    if not skill.default_contested and skill.default_source_count <= 1:
        flags.append("single-source-default")
    if skill.consensus_topics == 0:
        flags.append("no-consensus")
    return SkillCoverage(
        skill_id=skill.id,
        slug=skill.slug,
        status=skill.status.value,
        citation_count=skill.citation_count,
        distinct_sources=skill.distinct_sources,
        confidence_tier=skill.confidence_tier,
        flags=tuple(flags),
    )


def audit_sample(
    skills: Sequence[AuthoredSkill],
    *,
    sample_size: int = 3,
    rng: random.Random | None = None,
    drafts_only: bool = True,
) -> AuditReport:
    """Draw a reproducible review sample and compute its coverage. Pure (given an injected ``rng``).

    Args:
        skills: the authored-skill set to audit over.
        sample_size: how many skills to surface for manual review (the 10–20% spot-check).
        rng: the injected randomness — pass a seeded ``random.Random`` for a reproducible sample (tests +
            an auditable "these exact N" trail). ``None`` => a fresh ``Random()`` (non-reproducible).
        drafts_only: sample only un-promoted skills (you audit BEFORE promotion) when True.

    Returns:
        An :class:`AuditReport` with the sampled coverage rows + the corpus-wide roll-up.
    """
    rng = rng or random.Random()
    pool = [s for s in skills if (not drafts_only or s.status is SkillStatus.DRAFT)]
    # deterministic candidate order before sampling, so the seed fully determines the draw
    pool_sorted = sorted(pool, key=lambda s: s.id)
    k = min(sample_size, len(pool_sorted))
    drawn = rng.sample(pool_sorted, k) if k > 0 else []
    drawn.sort(key=lambda s: s.id)

    rows = tuple(coverage(s) for s in drawn)
    flagged = sum(1 for r in rows if r.flags)
    return AuditReport(
        sampled=rows,
        total_skills=len(skills),
        draft=sum(1 for s in skills if s.status is SkillStatus.DRAFT),
        promoted=sum(1 for s in skills if s.status is SkillStatus.PROMOTED),
        flagged=flagged,
        sample_size=k,
    )
