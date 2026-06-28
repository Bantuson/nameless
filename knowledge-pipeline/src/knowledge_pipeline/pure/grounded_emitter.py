"""``emit_grounded_skill_md`` — render a gated, decomposition-grounded skill into a LOW-confidence SKILL.md.

The Phase-6 sibling of :mod:`knowledge_pipeline.pure.layered_emitter`. It renders the SAME layered body the
Phase-5 emitter does (default / consensus / contested / citations) — reusing that module's helpers so the
two stay consistent — but adds the two things a sparse-genre skill MUST carry to be honest (KNOW-10):

  * **a forced ``confidence: LOW`` stamp** in the frontmatter + a one-line grounding banner that says, in
    plain words, "grounded by decomposition + audio analysis, NOT direct tutorials" (PITFALLS #4). A
    decomposition default can rest on 3 corroborating tracks and *look* HIGH; this emitter refuses to let
    that indirect, thin evidence read as settled craft.
  * **a ``## Grounding`` section** that shows its work: the parent techniques it was composed from, the
    NEGATIVE SPACE (what the subgenre omits/breaks vs its parents — the real identity), and the actual
    released tracks whose measured signatures corroborated it (artist · title, by ``audio:`` record id).

Kept PURE (objects in, string out) and run ONLY after the citation gate passes — the markdown is decoration
over already-verified content, never a place new craft can enter.
"""

from __future__ import annotations

from typing import Sequence

from ..domain.grounding import AudioAnalysisRecord, DecompositionMap
from ..domain.skills import SkillDraft, SkillStatus
from .layered_emitter import (
    _DRAFT_BANNER,
    _PROMOTED_BANNER,
    _citation_lines,
    _mmss,
    _ordered_topics,
    _title,
)


def emit_grounded_skill_md(
    draft: SkillDraft,
    decomposition: DecompositionMap,
    records: Sequence[AudioAnalysisRecord],
    *,
    status: SkillStatus = SkillStatus.DRAFT,
    confidence: str = "LOW",
    grounding_note: str = "",
) -> str:
    """Render ``draft`` as a LOW-confidence, decomposition-grounded SKILL.md string. Pure (KNOW-10)."""
    cell = draft.cell
    default = draft.default
    consensus = draft.consensus_sections()
    conflicts = draft.conflict_sections()

    lines: list[str] = []

    # ---- frontmatter (valid Claude-skill: name + description; confidence FORCED low; grounded flag) ----
    lines.append("---")
    lines.append(f"name: {draft.name}")
    lines.append(f"description: {draft.description}")
    lines.append(f"status: {status.value}")
    lines.append(f"stage: {cell.stage}")
    lines.append(f"genre: {cell.genre}")
    lines.append(f"confidence: {confidence}")
    lines.append("grounded: true")
    lines.append(f"prompt_version: {draft.prompt_version}")
    lines.append("---")
    lines.append("")

    # ---- header + the honest grounding banner ----
    lines.append(f"# {_title(cell.genre, cell.stage)} — production skill (grounded)")
    lines.append("")
    audit_state = _DRAFT_BANNER if status is SkillStatus.DRAFT else _PROMOTED_BANNER
    note = grounding_note or (
        f"{confidence} confidence — grounded by parent-technique decomposition + audio analysis, "
        "NOT direct tutorials."
    )
    lines.append(f"> {note} {audit_state}")
    lines.append(
        "> Every assertion in **Default / Consensus / Contested** below is traceable to a cited tutorial "
        "claim (video @ timestamp) OR a measured audio analysis record (audio:<track>) and passed the "
        "citation gate — no claim or number in those layers was invented. The **Grounding** section is the "
        "editorial decomposition HYPOTHESIS (how this subgenre was composed from its parents): authored "
        "reasoning, NOT gated citations — read it as such. Nothing about melody, chords, or structure was "
        "taken from the reference tracks (measured surface only)."
    )
    lines.append("")

    # ---- grounding: how this skill was derived (the decomposition + the audio roster) ----
    lines.append("## Grounding — how this skill was derived")
    lines.append("")
    lines.append("_Editorial decomposition hypothesis — NOT gated citations. The parent-contribution and "
                 "negative-space notes below are authored reasoning about how this under-tutorialized "
                 "subgenre relates to its taught parents; they are not backed by individual tutorial "
                 "citations and did not pass the citation gate. The gated, cited evidence is in the "
                 "Default / Consensus / Contested / Citations layers._")
    lines.append("")
    lines.append("**Decomposed into parent techniques** (this subgenre is under-tutorialized, so it is "
                 "composed from its taught parents, never fabricated):")
    for p in decomposition.parents:
        lines.append(f"- **{p.label}** ({p.cell.genre} · {p.cell.stage}) — {p.contributes}")
    lines.append("")
    if decomposition.negative_space:
        lines.append("**Negative space** (what this subgenre deliberately omits or breaks vs its parents — "
                     "often the real identity):")
        for ns in decomposition.negative_space:
            lines.append(f"- {ns}")
        lines.append("")
    if records:
        lines.append(f"**Corroborated against {len(records)} measured track(s)** (non-melodic signatures "
                     "only; the records are the audio citations):")
        for r in sorted(records, key=lambda x: x.track_id):
            title = f" · {r.title}" if r.title else ""
            lines.append(f"- `{r.citation_id}` — {r.artist}{title}")
        lines.append("")

    # ---- default ----
    lines.append("## Default — act on this")
    lines.append("")
    lines.append(f"Default approach: {default.body.strip()}")
    if default.stance is not None:
        lines.append("")
        lines.append(
            f"_Sources disagree on this — the default reflects the better-corroborated **{default.stance}** "
            "camp; see Contested below before committing._"
        )
    lines.append("")
    if default.citations:
        lines.extend(_citation_lines(default.citations))
    else:
        lines.append("- (no citations)")
    lines.append("")

    # ---- consensus ----
    lines.append("## Consensus — corroborated across sources (tutorial + audio)")
    lines.append("")
    if consensus:
        for s in consensus:
            lines.append(f"### {s.technique} — {s.distinct_sources} source(s) agree")
            lines.append(s.body.strip())
            lines.extend(_citation_lines(s.citations))
            lines.append("")
    else:
        lines.append("_No uncontested corroboration in this cell — see Contested, or treat as low-coverage._")
        lines.append("")

    # ---- contested ----
    lines.append("## Contested — both camps preserved")
    lines.append("")
    if conflicts:
        for topic in _ordered_topics(conflicts):
            camps = [s for s in conflicts if s.topic == topic]
            lines.append(f"### {camps[0].technique} — contested ({len(camps)} camps)")
            for camp in camps:
                lines.append(f"**[{camp.stance}]** ({camp.distinct_sources} source(s)) {camp.body.strip()}")
                lines.extend(_citation_lines(camp.citations, indent="  "))
            lines.append(
                "_The opinionated default above takes a side; this block preserves the disagreement so the "
                "agent (and you) can reason about the trade-off rather than inherit a laundered consensus._"
            )
            lines.append("")
    else:
        lines.append("_No contested topics in this cell._")
        lines.append("")

    # ---- citations roll-up (tutorial video @ ts AND audio:<track> records, side by side) ----
    lines.append("## Citations")
    lines.append("")
    seen: set[str] = set()
    for s in draft.all_sections():
        for c in s.citations:
            if c.claim_id in seen:
                continue
            seen.add(c.claim_id)
            lines.append(f'- `{c.claim_id}`  {c.source_video_id} @ {_mmss(c.timestamp_ms)}  "{c.quote}"')
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"
