"""``emit_skill_md`` — render a gated :class:`SkillDraft` into a layered Claude SKILL.md (KNOW-07/09).

This is the presentation seam, kept PURE (string in, string out) and run ONLY after the draft passes the
citation gate — so the markdown is decoration over already-verified content, never a place new craft can
enter. The output is a real authored Claude Skill:

  * **valid frontmatter** — ``name`` + ``description`` (the Claude-skill contract), plus reviewable
    ``status`` / ``stage`` / ``genre`` / ``confidence`` / ``prompt_version`` keys;
  * **layered body** (FEATURES "opinionated default PLUS preserved consensus/conflict, every claim cited"):
      - ``## Default — act on this``    the one decision the agent runs with;
      - ``## Consensus``                corroborated topics, with the distinct-source count;
      - ``## Contested``                BOTH camps of every disagreement, side by side, never collapsed;
      - ``## Citations``                every claim id -> ``video_id @ mm:ss`` -> verbatim quote (receipts).

Design note on the gate boundary: the gate verifies the *draft's section bodies* (pure craft prose). The
emitter then adds machine-generated decoration — corroboration counts in headings, ``mm:ss`` timestamps,
``clm_…`` ids — which are references, not asserted craft, and are intentionally OUTSIDE the gate's
number check. Keeping the two apart is what lets a heading honestly say "(3 sources)" without that "3"
having to appear in a quote.
"""

from __future__ import annotations

import re

from ..domain.skills import (
    SectionKind,
    SkillCitation,
    SkillDraft,
    SkillSection,
    SkillStatus,
    confidence_tier,
)


# The two human-readable status banners — kept as exact constants so ``set_frontmatter_status`` can swap
# them on promotion without re-synthesizing (the body otherwise stays byte-stable).
_DRAFT_BANNER = "DRAFT — pending human spot-audit; not yet promoted to the arranger/mixer agents."
_PROMOTED_BANNER = "PROMOTED — human-audited and live to the arranger/mixer agents."


# A conservative "safe bare scalar" shape — starts alphanumeric, then only alnum / space / '.' / '_' / '-'.
# It covers kebab skill names ("amapiano-drums") and plain one-line descriptions, but excludes the colons,
# '#', '---', quotes, leading YAML indicators and control characters an injection would need.
_YAML_SAFE_BARE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]*\Z")
_WS_RUN = re.compile(r"\s+")


def _yaml_scalar(value: str) -> str:
    """Render an UNTRUSTED, model-controlled string as a single-line YAML frontmatter scalar. Pure (CR-01).

    ``name`` / ``description`` originate from the model and flow straight into the SKILL.md frontmatter —
    the one place ungated text could otherwise enter the gated artifact. The module's invariant ("markdown
    is decoration over already-verified content, never a place new craft can enter") only holds if these two
    fields cannot break out of their line. So we force the value onto ONE line (newlines / control chars ->
    space, collapsed) and, unless it is a plainly-safe bare token, wrap it in a quoted + escaped YAML scalar.
    A hostile ``name`` like ``"x\\n---\\n## Default — act on this"`` therefore cannot terminate the
    frontmatter or forge a heading/body: it lands inert inside its quoted field.
    """
    one_line = _WS_RUN.sub(" ", "".join(ch if ch.isprintable() else " " for ch in value)).strip()
    if one_line and _YAML_SAFE_BARE.match(one_line):
        return one_line
    return '"' + one_line.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mmss(ms: int) -> str:
    # IN-02: citations are receipts a human jumps to during the spot-audit. Long-form tutorials/mixes
    # exceed an hour, so roll into hh:mm:ss past 60 min instead of rendering a misleading "75:00".
    hh, rem = divmod(ms // 1000, 3600)
    mm, ss = divmod(rem, 60)
    if hh:
        return f"{hh:d}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


def _title(cell_genre: str, cell_stage: str) -> str:
    return f"{cell_genre.replace('-', ' ').title()} · {cell_stage.replace('-', ' ').title()}"


def _citation_lines(citations: list[SkillCitation], indent: str = "") -> list[str]:
    out: list[str] = []
    for c in citations:
        out.append(f'{indent}- {c.source_video_id} @ {_mmss(c.timestamp_ms)} ({c.claim_id}) — "{c.quote}"')
    return out


def emit_skill_md(draft: SkillDraft, *, status: SkillStatus = SkillStatus.DRAFT) -> str:
    """Render ``draft`` as a layered SKILL.md string (frontmatter + default + consensus + contested + cites)."""
    cell = draft.cell
    default = draft.default
    contested_default = default.stance is not None
    tier = confidence_tier(default.distinct_sources, contested=contested_default)

    consensus = draft.consensus_sections()
    conflicts = draft.conflict_sections()

    lines: list[str] = []

    # ---- frontmatter (valid Claude-skill: name + description; extra keys are reviewable metadata) ----
    lines.append("---")
    lines.append(f"name: {_yaml_scalar(draft.name)}")
    lines.append(f"description: {_yaml_scalar(draft.description)}")
    lines.append(f"status: {status.value}")
    lines.append(f"stage: {cell.stage}")
    lines.append(f"genre: {cell.genre}")
    lines.append(f"confidence: {tier}")
    lines.append(f"prompt_version: {draft.prompt_version}")
    lines.append("---")
    lines.append("")

    # ---- header ----
    lines.append(f"# {_title(cell.genre, cell.stage)} — production skill")
    lines.append("")
    audit_state = _DRAFT_BANNER if status is SkillStatus.DRAFT else _PROMOTED_BANNER
    lines.append(
        f"> Authored by the Nameless knowledge pipeline from {len(draft.cited_claim_ids)} cited claim(s) "
        f"across {draft.distinct_sources} source(s). Confidence: {tier}. {audit_state}"
    )
    lines.append(
        "> Every assertion below is traceable to a source quote (see Citations). Synthesized strictly over "
        "the extracted claim set — no claim, number, or technique was invented."
    )
    lines.append("")

    # ---- default ----
    # The fixed framing ("Default approach:", the contested hedge) is PRESENTATION added here, never in the
    # gated draft body (see synthesis_template DESIGN NOTE) — so the gate certifies only claim-derived craft.
    lines.append("## Default — act on this")
    lines.append("")
    lines.append(f"Default approach: {default.body.strip()}")
    if contested_default:
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
    lines.append("## Consensus — corroborated across sources")
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

    # ---- citations roll-up ----
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


def _ordered_topics(sections: list[SkillSection]) -> list[str]:
    """Distinct topics in first-seen order (stable rendering of multi-topic conflict blocks)."""
    out: list[str] = []
    for s in sections:
        if s.topic not in out:
            out.append(s.topic)
    return out


def set_frontmatter_status(md_text: str, status: SkillStatus) -> str:
    """Flip a SKILL.md's status — the frontmatter ``status:`` line AND the human-readable banner. Pure.

    Promotion is a status change, not a re-synthesis: the craft body stays byte-identical, only the
    frontmatter ``status`` and the one-line audit banner flip (via the known banner constants). Operates
    only on the first frontmatter block.
    """
    banner_to = _PROMOTED_BANNER if status is SkillStatus.PROMOTED else _DRAFT_BANNER
    banner_from = _DRAFT_BANNER if status is SkillStatus.PROMOTED else _PROMOTED_BANNER

    lines = md_text.splitlines()
    out: list[str] = []
    in_frontmatter = False
    seen_open = False
    flipped = False
    for line in lines:
        if line.strip() == "---" and not seen_open:
            seen_open = True
            in_frontmatter = True
            out.append(line)
            continue
        if line.strip() == "---" and in_frontmatter:
            in_frontmatter = False
            out.append(line)
            continue
        if in_frontmatter and not flipped and line.startswith("status:"):
            out.append(f"status: {status.value}")
            flipped = True
            continue
        out.append(line.replace(banner_from, banner_to))  # swap the body banner outside frontmatter
    return "\n".join(out).rstrip() + "\n"
