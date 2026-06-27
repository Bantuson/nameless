# Phase 5 — Synthesize + Verify the First Authored Skills — SUMMARY

**Status:** Complete (code-complete + tests RUN on the base env; live Claude synthesis env-gated, not run).
**Build mode:** course/learning per `.planning/ENGINEERING-PRINCIPLES.md` — real, complete code; verified by
review + tests-that-RUN against the fakes. No Anthropic API call, no `anthropic` install.

Phase 5 is the SYNTHESIZE half of the two-pass design: it turns the Phase-4 cited-claim layer into
**authored, layered Claude Skills** behind a **hard, pure citation gate**, emits the P1 north-star cells to
`skills/production/`, and gates promotion behind a **human spot-audit**. It extends the same
`knowledge-pipeline/` package, mirroring the Phase-3/4 ports + fakes + pure-core + LEARNING pattern exactly.

---

## File map

### New domain / pure (the testable heart — no I/O, no `anthropic`)
- `src/knowledge_pipeline/domain/skills.py` — `SkillStatus`, `SectionKind`, `ProductionCell`,
  `SkillCitation`, `SkillSection`, `SkillDraft`, `AuthoredSkill`, `SkillStats`, `compute_skill_id`,
  `confidence_tier`, and the **P1 grid data** (`P1_CELLS`, `NORTH_STAR_ORDER`).
- `src/knowledge_pipeline/domain/keys.py` *(extended)* — `numbers()` (the canonicalizing numeric-token
  extractor the gate's invented-number rule is built on).
- `src/knowledge_pipeline/pure/cell_selection.py` — `select_cells` / `clusters_for_cell` / `cell_priority`
  (P1 north-star ordering, KNOW-09).
- `src/knowledge_pipeline/pure/citation_gate.py` — **`citation_gate(draft, claims, *, snapshots) -> GateResult`**,
  the heart (KNOW-08): R1 uncited · R2 nonexistent-source/quote-tamper · **R3 invented-number** · R4
  ungrounded-assertion · R5 citation-rot (reuses Phase-4 `verify_citation`). A pure function, **not a port**.
- `src/knowledge_pipeline/pure/synthesis_template.py` — `template_synthesize` (deterministic layered
  synthesis; bodies are verbatim `claim_text`, structurally synthesis-only-over-claims, KNOW-07).
- `src/knowledge_pipeline/pure/layered_emitter.py` — `emit_skill_md` (frontmatter + Default + Consensus +
  Contested + Citations) and `set_frontmatter_status` (promotion).
- `src/knowledge_pipeline/pure/audit.py` — `coverage` + `audit_sample` (citation coverage, flags,
  reproducible seeded sample, KNOW-11).
- `src/knowledge_pipeline/pure/synthesis_schema.py` — `EMIT_SKILL_TOOL_SCHEMA` + `parse_synthesizer_output`
  (re-grounds every citation from the real claims) + `format_clusters_for_synthesis`.

### New ports / adapters / registry / prompt
- `src/knowledge_pipeline/ports.py` *(extended)* — `SkillSynthesizer`, `SkillStore` protocols.
- `src/knowledge_pipeline/adapters/skill_synthesizer_fake.py` — `FakeSkillSynthesizer` (delegates to the
  pure template; optional scripted).
- `src/knowledge_pipeline/adapters/skill_synthesizer_anthropic.py` — `AnthropicSkillSynthesizer`
  (`emit_skill` forced tool-use, `claude-opus-4-8`; **lazy** `import anthropic`; env-gated, NOT run).
- `src/knowledge_pipeline/adapters/skill_store_mem.py` — `InMemorySkillStore` (fake).
- `src/knowledge_pipeline/adapters/skill_store_fs.py` — `FilesystemSkillStore` (REAL — writes
  `skills/production/**/SKILL.md` + registry; sqlite/pathlib are stdlib).
- `src/knowledge_pipeline/adapters/__init__.py` *(extended)* — eager exports of the three stdlib P5 adapters.
- `src/knowledge_pipeline/skills_sql.py` — additive DDL (`skills`, `skill_citations`) extending
  `registry.sqlite`.
- `src/knowledge_pipeline/prompts.py` *(extended)* — `SYNTHESIS_PROMPT_VERSION` +
  `SYNTHESIS_SYSTEM_PROMPT_V1` (versioned: synthesize-only-over-claims, never invent numbers, cite all).

### Orchestration / CLI
- `src/knowledge_pipeline/synthesis_pipeline.py` — `SynthesisPipeline` (select → synthesize → **GATE** →
  emit → store) + `build_authored_skill`.
- `src/knowledge_pipeline/skills_cli.py` — `skills synthesize | list | show | audit | promote | stats`.
- `pyproject.toml` *(extended)* — version `0.5.0`, `skills` script entry point.

### Tests (all RUN on the base env — pydantic/pytest only)
- `tests/test_skill_domain.py` (5), `tests/test_cell_selection.py` (8), `tests/test_citation_gate.py` (10),
  `tests/test_synthesis_template.py` (8), `tests/test_layered_emitter.py` (7), `tests/test_audit.py` (6),
  `tests/test_skill_store.py` (8), `tests/test_synthesis_pipeline.py` (6), `tests/test_skills_cli.py` (6),
  `tests/test_skills_no_synthesis_boundary.py` (3), `tests/conftest.py` *(extended with P5 helpers/fixtures)*.

### Committed example skills (authored by the FAKE synthesizer, no API call — they PASS the gate)
- `skills/production/drums/amapiano/SKILL.md` — **the FLEX-vs-layered conflict preserved** + opinionated
  default on the flex-synth camp (LOW confidence, contested).
- `skills/production/bassline/deep-house/SKILL.md` — HIGH-confidence 3-source consensus default + a
  second consensus topic (sub-bass-mono).
- `skills/production/bassline/amapiano/SKILL.md`, `skills/production/bassline/rnb/SKILL.md` — 3-source
  consensus (cross-genre corroboration of the sub-bass high-pass).
- `skills/production/vocal-layering/rnb/SKILL.md` — the Sonder/Brent Faiyaz stacked-harmony signature
  (LOW, single-source — flagged honestly).

---

## Requirement coverage

| Req | What | Where |
|---|---|---|
| **KNOW-07** | Layered synthesis over the claim set (opinionated default + preserved consensus/conflict, every claim cited) | `synthesis_template.py`, `layered_emitter.py`, `synthesis_schema.py`, `prompts.py` |
| **KNOW-08** | The hard citation gate — every assertion/number traces to a cited quote; invented numbers / uncited / untraceable rejected | `citation_gate.py` (+ `keys.numbers`, reuses Phase-4 `verify_citation`) |
| **KNOW-09** | Authored skills, P1 north-star cells first, emitted to `skills/production/<stage>/<genre>/SKILL.md` | `cell_selection.py`, `domain/skills.py` (P1 grid), `skill_store_fs.py`, `synthesis_pipeline.py`, committed `skills/production/**` |
| **KNOW-11** | Human spot-audit; skills ship `status: draft`; `skills audit` (coverage + flags); `skills promote` human-gated | `audit.py`, `skills_cli.py` (`audit` / `promote --yes`), `skill_store_*.set_status` |

---

## The gate REJECT demonstration (the make-or-break payoff)

The gate is exercised both ways as fixtures (`tests/test_citation_gate.py`) and live on the CLI path:

- **Grounded draft → PASS.** A draft whose every number + assertion traces to a cited quote passes
  (`test_grounded_draft_passes_the_gate`).
- **Invented number → REJECT.** The same draft with `40 Hz` (no source said 40) →
  `invented_number: asserts number(s) ['40'] present in no cited source quote`.
- **Uncited / nonexistent-source / tampered-quote / hallucinated-craft / citation-rot → REJECT**, each as
  its own auditable reason code.
- **Pipeline-level proof:** `test_a_synthesizer_that_invents_a_number_is_rejected_by_the_gate` wires a
  deliberately-malicious synthesizer; **every** poisoned cell is rejected and **nothing is written** — the
  synthesizer (real or fake) gets no special pass.

Live console demonstration during the build:
```
grounded draft  -> PASS
invented numbers-> REJECT :: invented_number: asserts number(s) ['40', '7'] present in no cited source quote
```

---

## Verification (honest: reviewed/run vs env-gated)

### RUN here (RAM-safe, base env: pydantic + pytest only)
- **`uv run pytest -q` → 201 passed** (134 Phase 3+4 cumulative + **67 new Phase 5**), in ~6–8s, zero
  network/API/DB. Covers: cell selection + P1 ordering; the citation gate (grounded PASS + every reject
  path); the synthesis-only-over-claims invariant (numbers ⊆ claims, citations ⊆ claims); the layered
  emitter (3 blocks, both conflict camps, frontmatter, promotion banner); the skill store (in-memory **and
  the REAL filesystem+sqlite** round-trip); audit coverage + reproducible sample; promote (draft→promoted);
  synthesis e2e incl. the poisoned-synthesizer reject; the `skills` CLI; and the boundary test proving
  `anthropic` is never imported on the fake path.
- **Offline `skills synthesize --fixtures`** RUN: authored all 5 P1 cells, **rejected 0**, wrote the 5
  committed `skills/production/**/SKILL.md` files. `skills audit` and `skills promote --yes` RUN.
- **The committed example skills exist because they passed the gate** — the pipeline only writes files for
  drafts that pass, so the artifacts are themselves the proof.

### Env-gated (NOT run here — requires `ANTHROPIC_API_KEY` + metered tokens)
- `uv sync --extra extract` then `uv run skills synthesize --corpus-root … --skills-root .` — the REAL
  `AnthropicSkillSynthesizer` (`emit_skill` forced tool-use, `claude-opus-4-8`). The code is complete and
  reviewed; the SDK import is lazy; **no API call was made and `anthropic` was not installed.** The pure
  citation gate runs identically over the real output, so the live path inherits the same guarantee the
  tests prove on the fake path.

No claim is made that the LLM ran. The deliverable is complete, correct code + a real, gate-passing example.
