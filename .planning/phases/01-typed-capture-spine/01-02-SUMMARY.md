---
phase: 01-typed-capture-spine
plan: 02
subsystem: control-plane
tags: [rust, state-machine, exhaustive-match, provenance, invariant]
requires:
  - phase: 01-01
    provides: nameless-core fragment model + placeholder state/provenance
provides:
  - "Complete FragmentState(12) + Transition(10) + IllegalTransition"
  - "Single checked transition() (exhaustive match) + Fragment::apply (sole mutation chokepoint)"
  - "Provenance enum (human_recorded|ai_generated|derived|sampled)"
  - "480-triple transition matrix + named invariant tests"
affects: [phase-02-fragment-analysis, phase-08-stem-sampling]
tech-stack:
  added: []
  patterns: [exhaustive-match-state-machine, single-mutation-chokepoint]
key-files:
  created: ["crates/nameless-core/src/provenance.rs", "crates/nameless-core/src/state_machine.rs"]
  modified: ["crates/nameless-core/src/fragment.rs", "crates/nameless-core/src/lib.rs"]
key-decisions:
  - "Built in final form within Plan 01's core commit (no placeholder-then-replace churn); end-state matches the plan exactly."
  - "Place legal only from Analyzed (human/sampled/derived) or Promoted (ai); the only wildcard maps exclusively to the error."
patterns-established:
  - "The harness gates, the agent explores: illegal transitions are typed errors, not panics/no-ops."
requirements-completed: [CAP-05]
duration: 4min
completed: 2026-06-27
status: complete
---

# Phase 1 Plan 02: Typed Lifecycle State Machine Summary

**One exhaustive-match `transition()` (+ `Fragment::apply` as the sole state mutator) makes 'place an unanalyzed fragment' and 'place an ungated AI generation' unrepresentable — proven by a 480-triple matrix test plus named invariant tests (PRD §7).**

See the consolidated phase summary: [`01-SUMMARY.md`](./01-SUMMARY.md).

## Highlights
- `FragmentState` (12, both human + ai paths), `Transition` (10), `IllegalTransition{from,transition}` (thiserror).
- `transition(provenance, from, t)`: provenance-guarded edges; `Place` only from `Analyzed` (human/sampled/derived) or `Promoted` (ai); no `Generated → Placed` bypass; `Rejected` terminal.
- `Provenance` complete (sampled typed in for Phase 8; travels the human path).
- Tests: `test_full_transition_matrix`, `test_cannot_place_unanalyzed`, `test_ai_requires_eval_gate`, `test_sampled_travels_human_path`, `test_rejected_is_terminal`, `test_illegal_transition_reports_pair`, `test_apply_is_sole_mutation_path`.

## Commits
- `d4b8f01` (authored within the core commit).

## Verification
Reviewed-complete (tests written). Env-gated: `cargo test -p nameless-core` (pure logic, fits 4GB; needs rustup, absent here).

---
*Phase: 01-typed-capture-spine · Plan 02 · Completed 2026-06-27*
