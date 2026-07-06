---
phase: quick-260706-file-skill-synthesizer
plan: 01
subsystem: knowledge-pipeline
tags: [skill-synthesis, no-api, ports-and-adapters, cli, tdd, citation-gate]
requirements: [KNOW-07, KNOW-08]
dependency_graph:
  requires:
    - knowledge_pipeline.pure.synthesis_schema.parse_synthesizer_output (unchanged pure re-grounding path)
    - knowledge_pipeline.pure.cell_selection.select_cells / clusters_for_cell (the selection the skip seam scopes)
    - knowledge_pipeline.synthesis_pipeline.SynthesisPipeline (UNCHANGED — no per-cell error seam, hence scoping)
    - knowledge_pipeline.pure.citation_gate.citation_gate (UNCHANGED — judges file drafts identically)
  provides:
    - knowledge_pipeline.adapters.skill_synthesizer_file.FileSkillSynthesizer (SkillSynthesizer port, no-API)
    - knowledge_pipeline.adapters.skill_synthesizer_file.scope_clusters_to_cells + CellScopedClaimStore (the skip seam)
    - knowledge_pipeline.adapters.skill_synthesizer_file.draft_filename (collision-safe {stage}__{genre}.json)
    - '"skills synthesize --drafts-dir <dir>" CLI plane (real fs corpus + real sqlite claims + real fs skill store)'
  affects:
    - knowledge_pipeline.skills_cli (three run modes: live / --fixtures / --drafts-dir)
tech_stack:
  added: []
  patterns:
    - skip-via-selection-scoping (no per-cell error seam in SynthesisPipeline, so missing-file cells are
      scoped OUT of select_cells via a read-only claim-store view instead of raise-to-skip)
    - complete-claim-index invariant (CellScopedClaimStore never filters list_claims — the gate's R2/R5
      evidence base stays authoritative; only list_clusters is scoped)
    - no-template-fallback (structurally unusable file -> DraftFileError; nothing the human never drafted
      may be authored — deliberate divergence from the Anthropic adapter's fallback)
key_files:
  created:
    - knowledge-pipeline/src/knowledge_pipeline/adapters/skill_synthesizer_file.py
    - knowledge-pipeline/tests/test_skill_synthesizer_file.py
  modified:
    - knowledge-pipeline/src/knowledge_pipeline/adapters/__init__.py
    - knowledge-pipeline/src/knowledge_pipeline/skills_cli.py
decisions:
  - "Missing draft file = skip via selection scoping (CellScopedClaimStore trims cluster genre lists to
    cells with files) because SynthesisPipeline has NO per-cell error seam — zero pipeline edits"
  - "Present-but-broken file = fatal DraftFileError -> clean SystemExit naming the file (drafts mode only);
    content errors are authoring bugs to fix, not cells to silently drop"
  - "File payload shape IS the emit_skill tool input; parse_synthesizer_output reused verbatim with
    prompt_version=file-draft-v1 so citations re-ground from real claims and provenance is visible"
  - "Filename convention {normalize_key(stage)}__{normalize_key(genre)}.json — double underscore is
    unambiguous because normalize_key emits only [a-z0-9-]"
metrics:
  duration: "~12 minutes"
  completed: "2026-07-06"
  tasks: 2
  tests_added: 19
  full_suite: "304 passed (285 baseline + 19 new)"
status: complete
---

# Quick Task 260706: FileSkillSynthesizer + `skills synthesize --drafts-dir` Summary

**FileSkillSynthesizer adapter ingests Claude-Code-pre-drafted `{stage}__{genre}.json` emit_skill payloads
through the unchanged SynthesisPipeline — the pure citation_gate REJECTS invented numbers/uncited claims in
file drafts exactly as it would API output — wired to a new no-API `skills synthesize --drafts-dir` CLI
plane over the real fs corpus + real sqlite claim layer + real fs skill store, with missing-file cells
skipped via selection scoping (survivors byte-identical).**

## What Was Built

### Task 1 — FileSkillSynthesizer adapter + cell-scoping seam (commits 4336ef7 test, 84e4869 feat)

- `adapters/skill_synthesizer_file.py` (180 lines): structural `SkillSynthesizer` port implementation.
  - `draft_filename`: `{normalize_key(stage)}__{normalize_key(genre)}.json` — collision-safe because
    `normalize_key` emits only `[a-z0-9-]` (tested: `("drums","deep-house")` vs `("drums-deep","house")`
    map to different names). Path-safe by construction (no raw user input in the name).
  - Missing file → `FileNotFoundError` naming cell slug + expected path + re-run hint (defense-in-depth;
    unreachable under the scoped CLI plane).
  - Malformed JSON / wrong top-level type / parse-`None` payload → `DraftFileError` naming the file.
    Explicitly NO template fallback — a fallback would author content the human never drafted.
  - Valid payload → `parse_synthesizer_output(raw, cell, clusters, prompt_version="file-draft-v1")`
    verbatim — same normalization/re-grounding as the Anthropic adapter (parity asserted by test).
  - `scope_clusters_to_cells` (pure) + `CellScopedClaimStore`: the skip seam. Trims cluster genre lists to
    cells with draft files (frozen-model copies, never mutation); `list_claims` passes through UNFILTERED
    so the gate's claim index stays complete; everything else delegates via `__getattr__`.
- `adapters/__init__.py`: eager import + `__all__` entry + Phase-5 docstring line (marked REAL, not a fake).

### Task 2 — CLI plane + e2e + regression gate (commits 2e5cfea test, 79a880e feat)

- `skills_cli.py`: new `_drafts_plane` mirroring `_live_plane` minus the anthropic import and
  `ANTHROPIC_API_KEY` checks; validates the drafts dir exists (else `SystemExit` naming the path and what
  belongs there); performs the SAME `select_cells(clusters, p1_only=not args.all)` the pipeline performs,
  partitions by `has_draft`, prints one `SKIP <slug>: no draft file <filename> in <dir>` line per missing
  cell and one `WARNING: unused draft file <name>` line per non-matching `*.json` — both to stderr, so
  `--json` stdout stays machine-parseable. Dispatch: fixtures → drafts → live. `--fixtures` and
  `--drafts-dir` are mutually exclusive (argparse group). `_handle_synthesize` converts `DraftFileError`
  to a clean `SystemExit` in drafts mode only. Module docstring updated to three run modes.
- `synthesis_pipeline.py`, `pure/citation_gate.py`, `pure/layered_emitter.py`, `pure/synthesis_schema.py`:
  **zero diff** (verified via `git diff --stat`).

## Verification Results (actually run here)

| Check | Result |
|---|---|
| `uv run pytest tests/test_skill_synthesizer_file.py -q` | 19 passed |
| `uv run pytest -q` (full suite regression gate) | 304 passed (baseline was 285) |
| Base-install import `from knowledge_pipeline.adapters import FileSkillSynthesizer` | OK (no `extract` extra) |
| Task-commit diff scope (`git diff --stat 49c8dce..HEAD`) | only the 4 planned files |
| Gate-file diff (`synthesis_pipeline.py`, `pure/citation_gate.py`, `pure/layered_emitter.py`, `pure/synthesis_schema.py`) | empty |
| e2e with `ANTHROPIC_API_KEY` deleted, real fs corpus + real sqlite + real fs skill store | rc 0, `authored=5 rejected=0`, SKILL.md files on disk, `stats` shows 5 drafts |
| Gate parity (adapter + CLI level) | invented-number draft returned intact, REJECTED with `invented_number` |
| Skip output-invariance | survivors' `body_sha256` identical between all-files and skip runs |

## Commits

| Task | Commit | Type | Description |
|---|---|---|---|
| 1 | 4336ef7 | test | Failing adapter/scoping/gate-parity tests (TDD RED) |
| 1 | 84e4869 | feat | FileSkillSynthesizer adapter + cell-scoping seam + eager export (GREEN) |
| 2 | 2e5cfea | test | Failing `--drafts-dir` CLI e2e tests (TDD RED) |
| 2 | 79a880e | feat | `skills synthesize --drafts-dir` plane + parser group (GREEN) |

## Deviations from Plan

None - plan executed exactly as written, including the load-bearing design notes (skip-via-scoping instead
of raise-to-skip, loud abort on broken files, no template fallback, unfiltered `list_claims`).

## Deferred Items

- `knowledge-pipeline/uv.lock` is untracked (generated by a prior `uv run`, predates this session, neither
  tracked nor gitignored). Out of this plan's scope — decide separately whether to commit or gitignore it.

## Known Stubs

None. All code paths are wired end-to-end and exercised by tests against real stores.

## Threat Flags

None beyond the plan's threat model. All four `mitigate` dispositions were implemented and tested:
- T-q260706b-01: `draft_filename` composed only from `normalize_key` output; naming + collision tests.
- T-q260706b-02: citations re-grounded from the real claim set by `parse_synthesizer_output` (out-of-cell
  ids dropped); the gate's claim index stays complete (unfiltered `list_claims` asserted); R5 ran against
  real fs snapshots in the e2e.
- T-q260706b-03: invented-number draft REJECTED by the unchanged gate — proven at both adapter level
  (`citation_gate` direct) and CLI level (`REJECTED ... invented_number` in the report).
- T-q260706b-04: malformed JSON / wrong shape / unusable payload → `DraftFileError` → clean `SystemExit`
  naming the file; template fallback explicitly forbidden and tested.
- T-q260706b-05 (accept): zero new dependencies — adapter is stdlib + existing pure/domain code.

## TDD Gate Compliance

RED→GREEN sequence verified in git log for both tasks: `test` commit precedes `feat` commit;
RED runs confirmed failing (ModuleNotFoundError for Task 1; unrecognized `--drafts-dir` for Task 2)
before each implementation.

## Self-Check: PASSED

- FOUND: knowledge-pipeline/src/knowledge_pipeline/adapters/skill_synthesizer_file.py
- FOUND: knowledge-pipeline/tests/test_skill_synthesizer_file.py
- FOUND: commits 4336ef7, 84e4869, 2e5cfea, 79a880e on main
