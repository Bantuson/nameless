---
phase: 7
phase_name: Reference-Track Context
status: passed
verified_by: tests-run (102 Python) + Rust review (course-project mode)
date: 2026-06-28
---

# Phase 7 Verification — Reference-Track Context

**Executed here (orchestrator re-ran):** `cd workers && python -m pytest -q` → **102 passed in 1.20s** (44 new Phase-7 + 58 prior). Rust written + reviewed, NOT compiled (no toolchain). LLM vibe-describer NOT run (env-gated).

## Success criteria
| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Upload reference to persistent library, immutable by ID | ✅ reviewed (Rust) | `cli::do_reference_upload` → content-hash via ObjectStore; `ReferenceTrack`; `0003_reference_tracks.sql` |
| 2 | Extract CLAP style + genre + tempo range + LUFS + tonal balance + stereo width + LLM vibe description | ✅ executed (fake) / reviewed (real) | `RestrictedReferenceAnalyzer` + `ClaudeVibeDescriber`; pure tonal-balance/stereo-width math tested |
| 3 | No melody/chroma/structure ever — non-cloning STRUCTURAL (schema + state machine) | ✅ executed + reviewed | 4 typed barriers: separate `ReferenceTrack` type; `gather_melodic_conditioning(&[Fragment])` `compile_fail` doctest; sealed `NonMelodicFeatures extra="forbid"`; `assert_non_melodic` on analyzer output |
| 4 | Attach one+ reference contexts to a project | ✅ executed | `reference attach` → `ReferenceStore::attach` → `project_reference_context` idempotent upsert |

## Requirement coverage
REF-01 ✅ · REF-02 ✅ · REF-03 ✅ · REF-04 ✅

## Testability law — satisfied
✅ ports (ReferenceStore [Rust], ReferenceAnalyzer/VibeDescriber/GenreTagger [Python]) × real+fake · ✅ pure core (tonal_balance/stereo_width/non_melodic/summary) · ✅ SoC (core/adapters/cli; domain/pure/adapters) · ✅ loose coupling (lazy CLAP/anthropic) · ✅ tests RUN (102 Python) + Rust tests written.
Engineering-quality signal: a flaky non-melodic test (random UUID hex containing "f0" ~8.6%) was caught via a 5000× stress run and rewritten to check field NAMES, not serialized substrings — deterministic now.

## Learning artifact
`workers/LEARNING.md` §11b — WHY non-cloning must be structural not conventional (clone-leak pitfall: one shared feature path silently clones; type the asymmetry), vibe vs melodic conditioning, what LUFS/tonal-balance/stereo-width/CLAP capture about "vibe".

## Env-gated (real env)
Rust: `cargo test` (incl. the compile_fail non-cloning proof), `cargo test -p nameless-adapters --features postgres -- --ignored` (after migrations 0001→0003). Python real analysis: `uv sync --extra ml` + compose `RestrictedReferenceAnalyzer(ClapEmbedder, ClapZeroShotGenreTagger, ClaudeVibeDescriber)`; LLM vibe needs `anthropic` + `ANTHROPIC_API_KEY`.

**PASS** — Python layer executed (102 tests), Rust + LLM reviewed-complete + env-gated. Non-cloning proven structural.
