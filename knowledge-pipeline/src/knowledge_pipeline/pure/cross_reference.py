"""``cross_reference`` — PURE consensus/conflict clustering (KNOW-06), the heart of Phase 4.

Groups atomic claims by topic (``(stage, technique)``) and partitions each topic into **consensus**
(uncontested) XOR **conflicts** (contested), preserving BOTH sides of every disagreement as first-class
data. This is the answer to the project's central GIGO fear (PITFALLS #3): when two producers disagree
(amapiano log-drum on FLEX vs layered samples), a naive pipeline silently averages them into mush or
picks one arbitrarily. Here the disagreement is *recorded*, never deleted, and **no opinionated default
is chosen** — that is Phase 5's job, made on top of this evidence.

The rule (deterministic, no LLM, no I/O):
  1. group claims by ``claim.topic`` (normalized ``stage/technique``).
  2. a topic is **contested** iff ≥2 DISTINCT normalized stances appear among its claims.
  3. contested  -> all claims go to ``conflicts`` (both camps survive).
     uncontested -> all claims go to ``consensus`` (corroboration).
  4. corroboration is measured by DISTINCT sources (``ClaimCluster.distinct_consensus_sources``), so a
     single creator repeating themselves never looks like agreement.

No-synthesis invariant (tested): ``cross_reference`` never merges a conflict into one claim, never emits
a "best way" field, and never drops a claim. ``len(consensus)+len(conflicts)`` always equals the number
of input claims for that topic.
"""

from __future__ import annotations

from typing import Sequence

from ..domain.claims import Claim, ClaimCluster
from ..domain.keys import normalize_key


def cross_reference(claims: Sequence[Claim]) -> list[ClaimCluster]:
    """Cluster claims into per-topic consensus/conflict, preserving every claim. Pure.

    Args:
        claims: the full claim set to cross-reference (ideally already deduped — see
            :func:`knowledge_pipeline.pure.claim_dedup.dedup_claims`).

    Returns:
        One :class:`ClaimCluster` per distinct topic, sorted by topic key (stable, deterministic).
        Contested topics keep both sides in ``conflicts``; uncontested topics put corroborating claims
        in ``consensus``.
    """
    groups: dict[str, list[Claim]] = {}
    for c in claims:
        groups.setdefault(c.topic, []).append(c)

    clusters: list[ClaimCluster] = []
    for topic in sorted(groups):
        members = groups[topic]
        distinct_stances = {normalize_key(c.stance) for c in members if c.stance and c.stance.strip()}
        contested = len(distinct_stances) >= 2

        genres = sorted({g for c in members for g in c.genre})
        # representative stage/technique (members share a normalized topic; take the first raw labels)
        stage = members[0].stage
        technique = members[0].technique

        if contested:
            consensus: list[Claim] = []
            conflicts: list[Claim] = list(members)
        else:
            consensus = list(members)
            conflicts = []

        clusters.append(
            ClaimCluster(
                topic=topic,
                stage=stage,
                technique=technique,
                genre=genres,
                consensus=consensus,
                conflicts=conflicts,
            )
        )
    return clusters
