# Phase 5: Synthesize + Verify the First Authored Skills - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous). Build mode: course-project per `.planning/ENGINEERING-PRINCIPLES.md`.

<domain>
## Phase Boundary

The SYNTHESIS half + the hard CITATION GATE + the first authored Claude Skills. Synthesize ONLY over the Phase-4 extracted claim set into layered SKILL.md (opinionated default + preserved consensus/conflict evidence, every claim cited); a programmatic citation-verification gate rejects anything not traceable to a real source quote/timestamp (no invented numbers); emit the P1 north-star cells to `skills/production/`; human spot-audit before promotion. This is the make-or-break payoff of the two-pass design.

Out of scope: sparse-genre grounding (Phase 6), reference/sampling (7-8), UI (9), generation/M1.
</domain>

<decisions>
## Implementation Decisions

### Architecture (ports-and-adapters — testability law)
- `SkillSynthesizer` port: `ClaimCluster[] → SkillDraft` (layered content). Real adapter = Claude (`claude-opus-4-8`, structured) constrained to synthesize ONLY over the provided claims; fake = deterministic template-based synthesizer (selects the best-corroborated claim as the default, lists consensus + conflicts, carries citations). API call = env-gated.
- `SkillStore` port: authored skills + audit/promotion status. Real (filesystem `skills/production/` + registry) + in-memory fake.
- `SynthesisPipeline` = pure orchestration: select P1 cells → synthesize per cell → **GATE** → emit draft → (human audit) → promote.

### Citation-verification GATE (KNOW-08 — pure, the heart)
- `citation_gate(skill_draft, corpus/claims) → Pass | Rejected[reasons]`. Rules (all pure, all tested):
  - every asserted claim/number must trace to a cited claim whose quote actually contains it (reuse Phase-4 `verify_citation`);
  - **reject invented numbers** — any numeric token in the skill not present in a cited source quote;
  - no claim without a citation; no citation pointing at a non-existent/uncorroborated source.
- A draft that fails the gate is REJECTED, never shipped. This is the programmatic answer to "quality in, quality out".

### Layered output format (KNOW-07)
- SKILL.md template: an opinionated DEFAULT per technique (for the agent to act on) + a "Consensus" block + a "Contested / conflicts" block (both camps preserved, e.g. amapiano log-drum FLEX-vs-layered) + per-claim citations (video_id @ ts). Synthesis is strictly over the claim set — no new claims.

### Emit authored skills (KNOW-09)
- `skills/production/<stage>/<genre>/SKILL.md` = the "production stack of skill"; author the P1 north-star cells first (R&B vocal layering/adlibs/lush chords/atmosphere; amapiano & alt-piano log-drum/groove + jazzy piano; deep-house space/groove).
- **Produce at least one REAL example SKILL.md** from the Phase-4 fixture claims via the FAKE synthesizer (deterministic) — committed, passing the gate — so a tangible authored skill exists without calling the API.

### Human spot-audit (KNOW-11)
- Skills are emitted as `status: draft`; a `skills audit` flow shows a sampled set with citation-coverage + flags; promotion (`draft → promoted`) is human-gated (a CLI confirm). Nothing ships unaudited.

### Claude's Discretion
- SKILL.md exact structure (must match Claude-skill conventions: frontmatter name/description + body), registry schema, default-selection heuristic, synthesis prompt wording.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 4 `knowledge-pipeline/`: `Claim`/`ClaimCluster`, `verify_citation`, `cross_reference`, claim fixtures (R&B/amapiano consensus + FLEX-vs-layered conflict), claim store, the ports+fakes+pure-core+LEARNING pattern. EXTEND this package.
- `.planning/research/FEATURES.md` (the production-stack-of-skill taxonomy + P1 cells; layered opinionated-default + consensus/conflict) and `PITFALLS.md` (citation gate, never invent numbers, human spot-audit before ship).
- Claude-skill authoring conventions (SKILL.md frontmatter `name`/`description` + progressive-disclosure body).

### Established Patterns
- Protocol ports + real+fake; pure-function core tested with fixtures; lazy heavy imports (anthropic only in real synthesizer); pydantic boundaries; tests RUN on the base env.

### Integration Points
- Input = Phase-4 claims + clusters (registry.sqlite). Output = `skills/production/**/SKILL.md` — the authored Claude Skills that (per PRD §12) teach the M1 arranger/mixer agents. Phase 6 adds sparse-genre (alt-piano) skills on top.
</code_context>

<specifics>
## Specific Ideas

- **Build mode: `.planning/ENGINEERING-PRINCIPLES.md`.** Course/learning — write the real Claude synthesizer; DO NOT call the API/install. Verify by review + tests-that-RUN against the FAKE synthesizer + fixtures: the citation gate (PASS on grounded draft, REJECT on an invented-number/uncited draft — both as fixtures), layered emitter, P1 selection, audit/promote status. Real synthesis is env-gated (`ANTHROPIC_API_KEY` + tokens).
- **Extend `LEARNING.md`** teaching: synthesis-ONLY-over-claims discipline; how the citation gate catches invented numbers + hallucinated craft; why layered output (opinionated default the agent acts on + preserved evidence for trust); why a human spot-audit before any skill ships. This closes the GIGO story end-to-end.
- The committed example SKILL.md is itself a teaching artifact — show the layered format concretely.
</specifics>

<deferred>
## Deferred Ideas
- Sparse-genre (alt-piano) grounding via decomposition + released-track audio → Phase 6.
- Broad genre×stage coverage (P2 cells), non-tutorial mining → v2.
</deferred>
