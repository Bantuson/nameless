---
phase: quick-260706-file-claim-extractor
plan: 01
subsystem: knowledge-pipeline
tags: [claim-mining, no-api, ports-and-adapters, cli, tdd]
requirements: [KNOW-05]
dependency_graph:
  requires:
    - knowledge_pipeline.pure.extraction_schema.parse_extractor_output (unchanged pure normalizer)
    - knowledge_pipeline.adapters.corpus_fs._safe_video_id (reused P3 CR-01 traversal guard)
    - knowledge_pipeline.mining_pipeline.MiningPipeline (UNCHANGED — per-video extractor-exception catch)
  provides:
    - knowledge_pipeline.adapters.claim_extractor_file.FileClaimExtractor (ClaimExtractor port, no-API)
    - "claims mine --mined-dir <dir>" CLI plane (real FilesystemCorpusStore + real SqliteClaimStore)
  affects:
    - knowledge_pipeline.claims_cli (three run modes: live / --fixtures / --mined-dir)
tech_stack:
  added: []
  patterns:
    - error-seam-via-exceptions (adapter raises precise exceptions; unchanged pipeline converts to per-video skip lines)
    - single-traversal-guard reuse (_safe_video_id imported from corpus_fs, never duplicated)
key_files:
  created:
    - knowledge-pipeline/src/knowledge_pipeline/adapters/claim_extractor_file.py
    - knowledge-pipeline/tests/test_claim_extractor_file.py
  modified:
    - knowledge-pipeline/src/knowledge_pipeline/adapters/__init__.py
    - knowledge-pipeline/src/knowledge_pipeline/claims_cli.py
decisions:
  - "Missing mined file raises FileNotFoundError (per-video skip via the pipeline's existing catch); malformed JSON raises ValueError naming the file — no pipeline changes needed"
  - "File payload shape IS the emit_claims tool input; parse_extractor_output reused verbatim so identity/citation fields bind from the transcript, never the file"
  - "Adapter docstrings avoid the word 'anthropic' entirely so the done-criterion grep is literally clean (no SDK import either)"
metrics:
  duration: "~7 minutes"
  completed: "2026-07-06"
  tasks: 2
  tests_added: 17
  full_suite: "285 passed (268 baseline + 17 new)"
status: complete
---

# Quick Task 260706: FileClaimExtractor + `claims mine --mined-dir` Summary

**FileClaimExtractor adapter ingests Claude-Code-pre-mined `{video_id}.json` claim files through the unchanged MiningPipeline (verify_citation/dedup/cross-reference identical to API output), wired to a new no-API `claims mine --mined-dir` CLI plane over the real filesystem corpus + real sqlite store.**

## What Was Built

### Task 1 — FileClaimExtractor adapter (commits 6bd7c20 test, 13d89af feat)

- `adapters/claim_extractor_file.py` (84 lines): structural `ClaimExtractor` port implementation.
  - Empty transcript → `[]` without reading any file (mirrors the SDK extractor).
  - `_safe_video_id` reused from `corpus_fs` before any path composition (P3 CR-01; one guard, no drift).
  - Missing file → `FileNotFoundError` naming video id + expected path + a re-run hint; the unchanged
    `MiningPipeline` catch turns it into a per-video `extract error: ...` skip line.
  - Malformed JSON / wrong top-level type → `ValueError` naming the offending file (loud, run continues).
  - Valid payload → `parse_extractor_output(raw, transcript, genres=...)` verbatim — byte-for-byte the
    same normalization/re-anchoring path as the live SDK extractor (contract parity asserted by test:
    identical claim ids).
- `adapters/__init__.py`: eager import + `__all__` entry + Phase-4 docstring line (marked REAL, not a fake).

### Task 2 — CLI plane + e2e + regression gate (commits d4ab69a test, 4dd9a4f feat)

- `claims_cli.py`: new `_mined_plane` mirroring `_live_plane` minus the anthropic import and
  `ANTHROPIC_API_KEY` checks; validates the mined dir exists (else `SystemExit` naming the path);
  identical target selection (`--video` list, else `list_entries()` filtered to `KEEP_VERDICTS` with
  discovery-genre provenance). Dispatch: fixtures → mined → live. `--fixtures` and `--mined-dir` are
  mutually exclusive (argparse group). Module docstring updated to three run modes.
- `MiningPipeline`, `pure/citation.py`, `pure/citation_gate.py`: **zero diff** (verified).

## Verification Results (actually run here)

| Check | Result |
|---|---|
| `uv run pytest tests/test_claim_extractor_file.py -q` | 17 passed |
| `uv run pytest -q` (full suite regression gate) | 285 passed (baseline was 268) |
| Base-install import `from knowledge_pipeline.adapters import FileClaimExtractor` | OK (no `extract` extra) |
| `grep -ci anthropic` on the new adapter module | 0 |
| Feat-commit diff scope | only the 4 planned files |
| Gate-file diff (`mining_pipeline.py`, `pure/citation*.py`) | empty |
| e2e with `ANTHROPIC_API_KEY` deleted, real FS corpus + real sqlite | rc 0, `citations_ok > 0` per video, stats persisted |

## Commits

| Task | Commit | Type | Description |
|---|---|---|---|
| 1 | 6bd7c20 | test | Failing adapter/unit/integration tests (TDD RED) |
| 1 | 13d89af | feat | FileClaimExtractor adapter + eager export (GREEN) |
| 2 | d4ab69a | test | Failing `--mined-dir` CLI e2e tests (TDD RED) |
| 2 | 4dd9a4f | feat | `claims mine --mined-dir` plane + parser group (GREEN) |

## Deviations from Plan

None - plan executed exactly as written. One phrasing choice worth noting: the plan's action text
suggested naming the Anthropic adapter in docstrings, while the done criterion required a literal
`grep "anthropic"` on the new module to find nothing — the done criterion won; docstrings say
"the live SDK extractor" instead.

## Known Stubs

None. All code paths are wired end-to-end and exercised by tests against real stores.

## Threat Flags

None beyond the plan's threat model. All three `mitigate` dispositions were implemented and tested:
- T-q260706-01: `_safe_video_id` reuse + parametrized traversal tests (`..`, `a/b`, `a\b`, empty).
- T-q260706-02: identity/citation fields bound from the transcript via `parse_extractor_output`;
  `verify_citation` proven to run on file-mined claims (`citations_ok > 0` asserted).
- T-q260706-03: malformed JSON → loud `ValueError` naming the file; per-video pipeline catch bounds
  blast radius (missing-file test proves the run completes and persists the other video).
- T-q260706-04 (accept): zero new dependencies — adapter is stdlib + existing pure code.

## TDD Gate Compliance

RED→GREEN sequence verified in git log for both tasks: `test` commit precedes `feat` commit;
RED runs confirmed failing (ModuleNotFoundError for Task 1; unrecognized `--mined-dir` for Task 2)
before each implementation.

## Self-Check: PASSED

- FOUND: knowledge-pipeline/src/knowledge_pipeline/adapters/claim_extractor_file.py
- FOUND: knowledge-pipeline/tests/test_claim_extractor_file.py
- FOUND: commits 6bd7c20, 13d89af, d4ab69a, 4dd9a4f on main
