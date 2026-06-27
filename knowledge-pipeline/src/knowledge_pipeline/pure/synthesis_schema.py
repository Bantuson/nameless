"""Synthesis tool-schema + re-grounding — the structured boundary between Claude and the typed SkillDraft.

Mirrors Phase-4's ``extraction_schema``: "reliable LLM output comes from structure, not clever prose."
This module is PURE (no ``anthropic`` import, no I/O) so the real synthesizer and the tests share one
definition of what the model may emit and how its output is re-grounded:

  * :data:`EMIT_SKILL_TOOL_SCHEMA` — the closed JSON Schema for the ``emit_skill`` tool. The model fills a
    typed object: a ``default`` block and ``sections``, each citing claims **by id only**. There is
    nowhere to write a quote, a timestamp, or a source — so the model cannot fabricate a citation; it can
    only *reference* claims that already exist.
  * :func:`format_clusters_for_synthesis` — renders the cell's claims (id, quote, stance, corroboration)
    as the user content. This IS the entire evidence base; the prompt forbids going beyond it.
  * :func:`parse_synthesizer_output` — validates the tool input and RE-GROUNDS every citation from the
    real claim set: the body is the model's prose, but each :class:`SkillCitation`'s quote / timestamp /
    source come from the looked-up :class:`Claim`, never the model. A referenced id that is not in the
    cell's claims is dropped. The model proposes; this code disposes — then the citation gate proves it.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, Field, ValidationError

from ..domain.claims import Claim, ClaimCluster
from ..domain.skills import (
    ProductionCell,
    SectionKind,
    SkillCitation,
    SkillDraft,
    SkillSection,
)

EMIT_SKILL_TOOL_NAME = "emit_skill"

# A single skill object. additionalProperties:false everywhere so the model cannot smuggle a fabricated
# quote/timestamp/source — citations are id REFERENCES into the provided claim set, re-grounded on parse.
EMIT_SKILL_TOOL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "description": "Kebab skill name, e.g. 'amapiano-drums'."},
        "description": {
            "type": "string",
            "description": "One sentence: what craft this skill teaches + when to load it. No numbers unless cited.",
        },
        "default": {
            "type": "object",
            "additionalProperties": False,
            "description": "The opinionated default the agent acts on — a decision ON TOP of the evidence.",
            "properties": {
                "body": {
                    "type": "string",
                    "description": "The default guidance, composed ONLY from the cited claims. Never invent a number.",
                },
                "claim_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ids of the claims this default rests on (must be from the provided set).",
                },
                "stance": {
                    "type": ["string", "null"],
                    "description": "If the default's topic is contested, the camp the default reflects; else null.",
                },
            },
            "required": ["body", "claim_ids"],
        },
        "sections": {
            "type": "array",
            "description": "Consensus blocks (uncontested topics) and conflict camps (one per side). Both sides kept.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["consensus", "conflict"]},
                    "topic": {"type": "string", "description": "The '<stage>/<technique>' key of the source cluster."},
                    "technique": {"type": "string"},
                    "stance": {"type": ["string", "null"], "description": "Required for a conflict camp; null for consensus."},
                    "body": {"type": "string", "description": "Prose composed ONLY from the cited claims."},
                    "claim_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "topic", "technique", "body", "claim_ids"],
            },
        },
    },
    "required": ["name", "description", "default", "sections"],
}


# ---- parsing / re-grounding ----------------------------------------------------------------


class _RawSectionIn(BaseModel):
    kind: str
    topic: str
    technique: str
    stance: Optional[str] = None
    body: str
    claim_ids: list[str] = Field(default_factory=list)


class _RawDefaultIn(BaseModel):
    body: str
    claim_ids: list[str] = Field(default_factory=list)
    stance: Optional[str] = None


class _RawSkillIn(BaseModel):
    name: str
    description: str
    default: _RawDefaultIn
    sections: list[_RawSectionIn] = Field(default_factory=list)


def claims_index(clusters: Sequence[ClaimCluster]) -> dict[str, Claim]:
    """All claims in a cell's clusters, keyed by id — the ONLY citations the model may reference. Pure."""
    idx: dict[str, Claim] = {}
    for cl in clusters:
        for c in cl.consensus + cl.conflicts:
            idx[c.id] = c
    return idx


def _ground_citations(claim_ids: Sequence[str], index: Mapping[str, Claim]) -> list[SkillCitation]:
    """Turn referenced ids into receipts built from the REAL claims; drop ids not in the cell. Pure."""
    out: list[SkillCitation] = []
    for cid in claim_ids:
        claim = index.get(cid)
        if claim is None:
            continue  # the model referenced a claim outside the cell — cannot fabricate it into existence
        out.append(
            SkillCitation(
                claim_id=claim.id,
                source_video_id=claim.source_video_id,
                timestamp_ms=claim.timestamp_ms,
                quote=claim.quote,
                technique=claim.technique,
                stance=claim.stance,
            )
        )
    return out


def parse_synthesizer_output(
    raw: dict,
    cell: ProductionCell,
    clusters: Sequence[ClaimCluster],
    *,
    prompt_version: str = "",
) -> Optional[SkillDraft]:
    """Validate the ``emit_skill`` tool input + re-ground every citation from the real claims. Pure.

    Returns ``None`` if the payload is structurally invalid or the default ends up with no real citation
    (an unsupported default must not become a draft — the gate would reject it anyway, but failing fast
    here keeps the bad output from being emitted at all).
    """
    index = claims_index(clusters)
    try:
        rs = _RawSkillIn.model_validate(raw)
    except ValidationError:
        return None

    default_cites = _ground_citations(rs.default.claim_ids, index)
    if not default_cites:
        return None
    default_topic = index[default_cites[0].claim_id].topic
    default_stage = index[default_cites[0].claim_id].stage
    default = SkillSection(
        kind=SectionKind.DEFAULT,
        topic=default_topic,
        technique=index[default_cites[0].claim_id].technique,
        stage=default_stage,
        genre=[cell.genre],
        stance=(rs.default.stance.strip() if rs.default.stance and rs.default.stance.strip() else None),
        body=rs.default.body.strip(),
        citations=default_cites,
        distinct_sources=len({c.source_video_id for c in default_cites}),
    )

    sections: list[SkillSection] = []
    for raw_sec in rs.sections:
        cites = _ground_citations(raw_sec.claim_ids, index)
        if not cites:
            continue  # an uncited section is not evidence; drop it
        try:
            kind = SectionKind(raw_sec.kind)
        except ValueError:
            continue
        if kind is SectionKind.DEFAULT:
            continue  # the default is emitted separately
        stage = index[cites[0].claim_id].stage
        sections.append(
            SkillSection(
                kind=kind,
                topic=raw_sec.topic.strip(),
                technique=raw_sec.technique.strip(),
                stage=stage,
                genre=[cell.genre],
                stance=(raw_sec.stance.strip() if raw_sec.stance and raw_sec.stance.strip() else None),
                body=raw_sec.body.strip(),
                citations=cites,
                distinct_sources=len({c.source_video_id for c in cites}),
            )
        )

    return SkillDraft(
        cell=cell,
        name=rs.name.strip() or cell.slug,
        description=rs.description.strip(),
        default=default,
        sections=sections,
        prompt_version=prompt_version,
    )


def format_clusters_for_synthesis(cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> str:
    """Render the cell's claims as the user content the real synthesizer sends. Pure / deterministic.

    Each line carries the claim id (what the model cites), its verbatim quote, stance, confidence, and the
    cluster's corroboration — the complete, and ONLY, evidence base. The model may synthesize over these
    and nothing else.
    """
    lines = [f"CELL: genre={cell.genre}  stage={cell.stage}", ""]
    for cl in clusters:
        kind = "CONTESTED" if cl.is_contested else "consensus"
        lines.append(f"TOPIC {cl.topic}  [{kind}]  ({_topic_sources(cl)} distinct source(s))")
        for c in cl.consensus + cl.conflicts:
            stance = f"  stance={c.stance}" if c.stance else ""
            lines.append(
                f'  - id={c.id}  conf={c.confidence:.2f}  src={c.source_video_id}@{c.timestamp_ms}ms{stance}\n'
                f'      claim: {c.claim_text}\n'
                f'      quote: "{c.quote}"'
            )
        lines.append("")
    return "\n".join(lines)


def _topic_sources(cl: ClaimCluster) -> int:
    return cl.distinct_consensus_sources + cl.distinct_conflict_sources
