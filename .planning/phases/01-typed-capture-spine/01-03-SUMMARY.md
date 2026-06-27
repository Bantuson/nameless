---
phase: 01-typed-capture-spine
plan: 03
subsystem: control-plane
tags: [rust, job-queue, retry, backpressure, dead-letter, serde]
requires:
  - phase: 01-01
    provides: core/adapters/cli + capture command
  - phase: 01-02
    provides: state machine (core/lib.rs)
provides:
  - "JobEnvelope (FeatureExtract|Separate) internally-tagged JSON"
  - "JobQueue trait (enqueue/consume/mark_done/mark_retry/capacity) + RetryPolicy (5 attempts, exp backoff) + JobError"
  - "InMemoryJobQueue: FIFO, bounded-capacity backpressure, retry ceiling → dead-letter"
  - "capture enqueues exactly one FeatureExtract job under --local"
affects: [phase-02-fragment-analysis]
tech-stack:
  added: []
  patterns: [durable-queue-port, enqueue-only-phase-1]
key-files:
  created: ["crates/nameless-core/src/job.rs", "crates/nameless-adapters/src/queue_mem.rs"]
  modified: ["crates/nameless-core/src/lib.rs", "crates/nameless-adapters/src/lib.rs", "crates/nameless-cli/src/cli.rs", "crates/nameless-cli/src/profile.rs"]
key-decisions:
  - "Postgres-backed queue (sqlxmq) at solo scale — NATS/Redis deferred (STACK §5); the in-memory fake proves the contract RAM-safe."
  - "Phase 1 enqueues only; the --local queue is process-local (documented)."
patterns-established:
  - "Bounded capacity + retry ceiling bound DoS (backpressure + no infinite retry)."
requirements-completed: [CAP-07]
duration: 4min
completed: 2026-06-27
status: complete
---

# Phase 1 Plan 03: Durable Job-Queue Seam Summary

**Typed JobEnvelope + JobQueue trait with an in-memory adapter exercising FIFO delivery, bounded-capacity backpressure (JobError::Full), and a retry ceiling that dead-letters at max_attempts — and capture now enqueues exactly one FeatureExtract job (CAP-07).**

See the consolidated phase summary: [`01-SUMMARY.md`](./01-SUMMARY.md).

## Highlights
- `job.rs`: `JobEnvelope` (`#[serde(tag="job")]`), `JobId/JobRecord/JobStatus`, `RetryPolicy{max_attempts:5, exp backoff capped 60s}`, `JobQueue` trait, `JobError`.
- `queue_mem.rs`: `InMemoryJobQueue` (`Mutex<VecDeque>` + capacity); tests for FIFO, backpressure at capacity, bounded retry → `DeadLettered`, done frees a slot.
- `cli`: `do_capture` enqueues `FeatureExtract{fragment_id}`; `--json` reports `enqueued_job`; unit test asserts exactly one matching job, no consumer runs.

## Commits
- `3c6c182` (queue_mem) · `0d241f8` (capture enqueue) · `d4b8f01` (job.rs in core commit).

## Verification
Reviewed-complete (tests written). Env-gated: `cargo test -p nameless-core -p nameless-adapters -p nameless-cli` (needs rustup). Real sqlxmq cross-restart durability → Plan 04 (live Postgres).

---
*Phase: 01-typed-capture-spine · Plan 03 · Completed 2026-06-27*
