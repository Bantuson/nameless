---
phase: 4
phase_name: Cited Claim Mining + Cross-Reference
status: passed
verified_by: tests-run (134 RAM-safe; 57 new) + review (course-project mode)
date: 2026-06-28
---

# Phase 4 Verification — Cited Claim Mining + Cross-Reference

**Executed here (orchestrator re-ran):** `cd knowledge-pipeline && PYTHONPATH=src python -m pytest -q` → **134 passed in 3.20s** (57 Phase-4 + 77 Phase-3 unchanged). The LLM was NOT called — a clean-subprocess test proves `anthropic`/`sentence_transformers` never load on the fakes path.

## Success criteria
| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Atomic claims, each bound to video_id+timestamp, typed stage×genre, NO synthesis | ✅ executed (fake) / reviewed (real) | `domain/claims.py`; real `claude-opus-4-8` forced `emit_claims` tool-use; identity/citation bound from transcript not model |
| 2 | Inspect any claim → trace to exact source quote + timestamp | ✅ executed | pure `verify_citation` (verified/drift/not_found); `claims show <id>` |
| 3 | Cross-reference groups by topic, preserves consensus AND conflict (never deleted) | ✅ executed | pure `cross_reference` (consensus XOR preserved conflict, distinct-source count); amapiano FLEX-vs-layered fixture; `claims list --conflicts` |

## Requirement coverage
KNOW-05 ✅ · KNOW-06 ✅

## No-synthesis boundary (tested invariant)
`tests/test_no_synthesis_boundary.py`: schema has no `default`/`recommended`/`best`/`winner` field; `cross_reference` never collapses a conflict; fake emits only verbatim-grounded `Claim` atoms. Offline e2e (real `SqliteClaimStore` + fake extractor): `mine --fixtures` → `claims=7 clusters=4 contested=1`, `citation_verified 7/7`.

## Testability law — satisfied
✅ ports (ClaimExtractor/SimilarityIndex/ClaimStore) × real+fake · ✅ pure core (citation/cross_reference/dedup/keys) · ✅ SoC · ✅ loose coupling (lazy heavy imports) · ✅ tests RUN (134).

## Learning artifact
`knowledge-pipeline/LEARNING.md` §§7–12 — structured tool-use vs free-form, the extract-THEN-synthesize split and why it defeats GIGO, citation discipline, consensus/conflict as first-class data, semantic-dedup trade-offs.

## Env-gated (real env)
`uv sync --extra extract` + `ANTHROPIC_API_KEY` → `uv run claims mine --corpus-root …` (claude-opus-4-8 forced tool-use; ~cents/video, idempotent upsert bounds re-run cost). Optional `uv sync --extra embed` for semantic dedup.

**PASS** — RAM-safe layer executed (134 tests), real LLM extractor reviewed-complete + env-gated.
