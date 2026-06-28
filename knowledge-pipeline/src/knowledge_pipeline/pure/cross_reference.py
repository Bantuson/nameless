"""``cross_reference`` — PURE consensus/conflict clustering (KNOW-06), the heart of Phase 4.

Groups atomic claims by topic (``(stage, technique)``) and partitions each topic into **consensus**
(uncontested) XOR **conflicts** (contested), preserving BOTH sides of every disagreement as first-class
data. This is the answer to the project's central GIGO fear (PITFALLS #3): when two producers disagree
(amapiano log-drum on FLEX vs layered samples), a naive pipeline silently averages them into mush or
picks one arbitrarily. Here the disagreement is *recorded*, never deleted, and **no opinionated default
is chosen** — that is Phase 5's job, made on top of this evidence.

The rule (deterministic, no LLM, no I/O):
  1. group claims by ``claim.topic`` (normalized ``stage/technique``).
  2. a topic is **contested** iff ≥2 DISTINCT normalized stances appear among its claims, OR its claims
     assert ≥2 DISTINCT non-empty number sets (divergent load-bearing parameters) — so a real
     disagreement the extractor left unstanced is never laundered into false consensus.
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
from ..domain.keys import normalize_key, numbers
from ..domain.models import CaptionSource


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
        # A topic is contested if its claims carry >=2 distinct stances OR its PRESCRIPTIVE (tutorial)
        # claims assert divergent load-bearing numbers (WR-03). The numeric signal catches a real
        # disagreement the extractor left UNSTANCED ("high-pass at 30 hz" vs "...40 hz", both stance=None)
        # which would otherwise be laundered into false consensus.
        #
        # It is scoped to caption-bearing (taught) claims on purpose: a tutorial number is a PRESCRIPTION,
        # so divergence is disagreement. A MEASURED audio claim (caption_source == NONE) carries a noisy
        # point estimate, and many tracks spread across a band is CORROBORATION, not conflict (PITFALLS
        # #5) — so measured numbers must never trip this signal. Number-free or same-numbered prescriptive
        # claims (incl. a stanced-vs-neutral pair) are likewise not forced into conflict.
        prescriptive = [c for c in members if c.caption_source is not CaptionSource.NONE]
        distinct_number_sets = {frozenset(numbers(c.claim_text)) for c in prescriptive}
        distinct_number_sets.discard(frozenset())  # number-free claims never signal a numeric conflict
        contested = len(distinct_stances) >= 2 or len(distinct_number_sets) >= 2

        genres = sorted({g for c in members for g in c.genre})
        # representative stage/technique. Members share a *normalized* topic key, so normalize the
        # representative labels too (IN-02) — otherwise the cluster would display whichever raw casing
        # the arbitrary first member happened to use ("Mixing" vs "mixing"), an inconsistency with the
        # topic key. normalize_key matches what topic_key already applied.
        stage = normalize_key(members[0].stage)
        technique = normalize_key(members[0].technique)

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
