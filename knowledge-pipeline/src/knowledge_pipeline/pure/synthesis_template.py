"""``template_synthesize`` — the PURE, deterministic layered synthesizer (KNOW-07).

This is the heart of the FAKE :class:`~knowledge_pipeline.ports.SkillSynthesizer`, and — like Phase-4's
``rule_based_extract`` — it is the reference behaviour the contract tests run against with no API. It turns
a cell's :class:`~knowledge_pipeline.domain.claims.ClaimCluster`s into a layered
:class:`~knowledge_pipeline.domain.skills.SkillDraft`:

  * an opinionated **default** (the decision the agent acts on), chosen ON TOP of the evidence by a small,
    reviewable heuristic — the best-corroborated topic, its highest-confidence claim; for a contested
    topic, the better-corroborated camp, with an explicit hedge pointing at the alternative;
  * a **consensus** section per uncontested topic (the corroborating claims, across distinct sources);
  * a **conflict** section per camp of every contested topic — BOTH camps preserved, never collapsed
    (the amapiano log-drum FLEX-vs-layered disagreement survives into the skill as first-class data).

THE INVARIANT that makes this safe (tested): **synthesis only over the claim set.** Every section ``body``
is composed *verbatim* from cited ``claim_text``; the only non-claim text is fixed connective template
prose that contains **no numbers and asserts no craft**. So this function is structurally incapable of
introducing a parameter or a claim the input clusters do not already contain — the citation gate then
proves it. No I/O, no LLM, fully deterministic.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..domain.claims import Claim, ClaimCluster
from ..domain.skills import (
    ProductionCell,
    SectionKind,
    SkillCitation,
    SkillDraft,
    SkillSection,
)

SYNTHESIS_TEMPLATE_VERSION = "skill-synthesis-template/v1"

# DESIGN NOTE — every gated ``body`` here is composed STRICTLY from verbatim ``claim_text`` (and nothing
# else): no connective prose, no template framing, no counts. That is deliberate. The citation gate checks
# each section body's numbers + token-coverage against its cited claims, so any non-claim word in the body
# would either tank the coverage check or smuggle in ungrounded content. Fixed framing — the "Default
# approach:" lead, the "sources disagree" hedge for a contested default — is PRESENTATION and is added by
# the layered emitter, OUTSIDE the gate. The opinionated decision lives in *which* claim/camp the template
# selects (and the ``stance`` it records), not in any prose the template writes.


def _claim_citation(claim: Claim) -> SkillCitation:
    return SkillCitation(
        claim_id=claim.id,
        source_video_id=claim.source_video_id,
        timestamp_ms=claim.timestamp_ms,
        quote=claim.quote,
        technique=claim.technique,
        stance=claim.stance,
    )


def _distinct_source_claims(claims: Sequence[Claim]) -> list[Claim]:
    """One representative claim per distinct source (highest confidence wins), source-stable order. Pure."""
    best: dict[str, Claim] = {}
    for c in claims:
        cur = best.get(c.source_video_id)
        if cur is None or c.confidence > cur.confidence:
            best[c.source_video_id] = c
    return [best[v] for v in sorted(best)]


def _topic_corroboration(cluster: ClaimCluster) -> int:
    return cluster.distinct_consensus_sources + cluster.distinct_conflict_sources


def _best_claim(claims: Sequence[Claim]) -> Claim:
    """Highest-confidence claim, tie-broken by (source, timestamp) for determinism. Pure."""
    return sorted(claims, key=lambda c: (-c.confidence, c.source_video_id, c.timestamp_ms))[0]


def _primary_cluster(clusters: Sequence[ClaimCluster]) -> Optional[ClaimCluster]:
    """The cluster the opinionated default is built on: best corroborated, then most confident. Pure."""
    if not clusters:
        return None
    return sorted(
        clusters,
        key=lambda cl: (
            -_topic_corroboration(cl),
            -max((c.confidence for c in (cl.consensus + cl.conflicts)), default=0.0),
            cl.topic,
        ),
    )[0]


def _consensus_section(cluster: ClaimCluster) -> SkillSection:
    reps = _distinct_source_claims(cluster.consensus)
    body = " ".join(c.claim_text.strip() for c in reps)
    return SkillSection(
        kind=SectionKind.CONSENSUS,
        topic=cluster.topic,
        technique=cluster.technique,
        stage=cluster.stage,
        genre=list(cluster.genre),
        body=body,
        citations=[_claim_citation(c) for c in reps],
        distinct_sources=cluster.distinct_consensus_sources,
    )


def _conflict_sections(cluster: ClaimCluster) -> list[SkillSection]:
    """One CONFLICT section per stance camp — both (or more) sides preserved. Pure."""
    out: list[SkillSection] = []
    for stance in sorted(cluster.sides().keys()):
        camp = cluster.sides()[stance]
        reps = _distinct_source_claims(camp)
        body = " ".join(c.claim_text.strip() for c in reps)
        out.append(
            SkillSection(
                kind=SectionKind.CONFLICT,
                topic=cluster.topic,
                technique=cluster.technique,
                stage=cluster.stage,
                genre=list(cluster.genre),
                stance=stance,
                body=body,
                citations=[_claim_citation(c) for c in reps],
                distinct_sources=len({c.source_video_id for c in camp}),
            )
        )
    return out


def _default_camp(cluster: ClaimCluster) -> tuple[str, list[Claim]]:
    """For a contested primary topic, the camp the default reflects: most sources, then most confident."""
    sides = cluster.sides()
    stance = sorted(
        sides,
        key=lambda s: (
            -len({c.source_video_id for c in sides[s]}),
            -max(c.confidence for c in sides[s]),
            s,
        ),
    )[0]
    return stance, sides[stance]


def _default_section(cell: ProductionCell, primary: ClaimCluster) -> SkillSection:
    """Build the opinionated DEFAULT from the primary cluster — a decision on top of the evidence. Pure."""
    if primary.is_contested:
        stance, camp = _default_camp(primary)
        reps = _distinct_source_claims(camp)
        chosen = _best_claim(camp)
        body = chosen.claim_text.strip()  # the chosen camp's claim, verbatim — framing is the emitter's job
        return SkillSection(
            kind=SectionKind.DEFAULT,
            topic=primary.topic,
            technique=primary.technique,
            stage=primary.stage,
            genre=list(primary.genre),
            stance=stance,
            body=body,
            citations=[_claim_citation(c) for c in reps],
            distinct_sources=len({c.source_video_id for c in camp}),
        )

    reps = _distinct_source_claims(primary.consensus)
    chosen = _best_claim(primary.consensus)
    body = chosen.claim_text.strip()  # the best-corroborated claim, verbatim
    return SkillSection(
        kind=SectionKind.DEFAULT,
        topic=primary.topic,
        technique=primary.technique,
        stage=primary.stage,
        genre=list(primary.genre),
        body=body,
        citations=[_claim_citation(c) for c in reps],
        distinct_sources=primary.distinct_consensus_sources,
    )


def _name(cell: ProductionCell) -> str:
    return cell.slug


def _description(cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> str:
    sources = len(
        {c.source_video_id for cl in clusters for c in (cl.consensus + cl.conflicts)}
    )
    topics = len(clusters)
    genre = cell.genre.replace("-", " ")
    stage = cell.stage.replace("-", " ")
    return (
        f"{genre} {stage} production craft, synthesized from {topics} cited topic(s) across {sources} "
        f"source(s). Opinionated default plus preserved consensus and contested evidence; every claim "
        f"cited (video @ timestamp). Load when arranging or mixing {genre} {stage}."
    )


def template_synthesize(cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> SkillDraft:
    """Deterministically synthesize a layered :class:`SkillDraft` for ``cell`` over its ``clusters``. Pure.

    Args:
        cell: the ``(stage, genre)`` leaf being authored.
        clusters: the clusters that belong to the cell (see ``cell_selection.clusters_for_cell``); must be
            non-empty (a cell with no evidence is never authored).

    Returns:
        A :class:`SkillDraft` whose every asserted number/word traces to a cited claim in ``clusters`` —
        the synthesis-only-over-claims invariant, then proven by the citation gate.
    """
    clusters = list(clusters)
    if not clusters:
        raise ValueError(f"cannot synthesize {cell.slug}: no clusters of evidence")

    primary = _primary_cluster(clusters)
    assert primary is not None  # non-empty clusters guarantee a primary

    default = _default_section(cell, primary)

    sections: list[SkillSection] = []
    for cl in clusters:
        if cl.is_contested:
            sections.extend(_conflict_sections(cl))
        elif cl.consensus:
            sections.append(_consensus_section(cl))

    return SkillDraft(
        cell=cell,
        name=_name(cell),
        description=_description(cell, clusters),
        default=default,
        sections=sections,
        prompt_version=SYNTHESIS_TEMPLATE_VERSION,
    )
