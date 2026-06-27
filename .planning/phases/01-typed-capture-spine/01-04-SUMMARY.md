---
phase: 01-typed-capture-spine
plan: 04
subsystem: control-plane
tags: [rust, postgres, sqlx, sqlxmq, s3, r2, migrations, feature-gated]
requires:
  - phase: 01-01
    provides: ObjectStore/FragmentRepo ports + CLI profile
  - phase: 01-02
    provides: Provenance + FragmentState enums (DB enum types must match)
  - phase: 01-03
    provides: JobQueue trait + JobEnvelope
provides:
  - "migrations/0001_init.sql: projects + fragments + provenance/fragment_state enum types; pgvector enabled"
  - "PostgresFragmentRepo (sqlx, compile-time-checked, text↔enum casts)"
  - "SqlxmqJobQueue (durable Postgres-backed enqueue)"
  - "S3ObjectStore (rust-s3 / R2, content-hash key, write-if-absent)"
  - "CLI server profile + .env.example — all behind the non-default `postgres` feature"
affects: [phase-02-fragment-analysis, phase-07-reference-context, phase-08-stem-sampling]
tech-stack:
  added: ["tokio (feature)", "sqlx 0.8 (feature)", "sqlxmq (feature)", "rust-s3 (feature)"]
  patterns: [feature-gated-heavy-leaf, sync-port-over-async-block_on-shim, text-enum-sql-cast-mapping]
key-files:
  created: ["migrations/0001_init.sql", ".env.example", "crates/nameless-adapters/src/{repo_pg,queue_sqlxmq,object_store_s3}.rs"]
  modified: ["crates/nameless-adapters/Cargo.toml", "crates/nameless-adapters/src/lib.rs", "crates/nameless-cli/Cargo.toml", "crates/nameless-cli/src/profile.rs"]
key-decisions:
  - "Heavy leaf behind a non-default `postgres` feature so the default + --local build stays 4GB-buildable."
  - "Sync ports over async adapters via an owned-runtime block_on shim contained in the feature-gated code."
  - "Postgres enum mapping via $n::text::provenance casts (read: provenance::text + from_db_str) — core stays sqlx-free, queries stay compile-time-checked."
  - "rust-s3 over aws-sdk-s3 (lighter tree for R2 via custom endpoint); swap is a one-file change behind the trait."
patterns-established:
  - "Same trait, swapped leaf: prod backends satisfy the Plan-01/03 ports unchanged."
requirements-completed: [CAP-02, CAP-07]
duration: 3min
completed: 2026-06-27
status: complete
---

# Phase 1 Plan 04: Production Heavy Leaf (Postgres/sqlxmq/R2) Summary

**Behind a non-default `postgres` feature: a sqlx PostgresFragmentRepo, a durable sqlxmq job queue, and an S3/R2 object store — plus the initial migration — all satisfying the Phase-1 ports without breaking the lean, 4GB-buildable default build.**

See the consolidated phase summary: [`01-SUMMARY.md`](./01-SUMMARY.md).

## Highlights
- `migrations/0001_init.sql`: `provenance`(4) + `fragment_state`(12) enum types matching the Rust enums exactly; `projects` + `fragments`; `create extension vector` (no embedding columns yet — Phase 2).
- `repo_pg.rs`: `query!`-checked SQL; enum labels bound as text + cast `$n::text::provenance`/`::fragment_state`; owned-runtime `block_on` shim bridges the sync `FragmentRepo`; `#[ignore]` live round-trip.
- `queue_sqlxmq.rs`: durable JSON enqueue (retries/backoff mirror `RetryPolicy`); consume/ack are the Phase-2 `JobRunner`'s job; `#[ignore]` cross-restart durability test.
- `object_store_s3.rs`: `rust-s3` R2 client, content-hash key, head-then-put immutability; `#[ignore]` live-bucket test.
- CLI server profile + `.env.example` gated behind the feature; `--local` remains the default.

## Commits
- `4751a35` (feature) · `1c95541` (fix: text↔enum bind).

## Verification
RAM-safe (the only dev-machine-checkable item): default `cargo build` pulls NO tokio/sqlx (feature gate intact). Env-gated (user's real env): `cargo build --features postgres`; `cargo sqlx migrate run`; `cargo sqlx prepare`/`SQLX_OFFLINE`; `--ignored` live Postgres + R2 tests. Commands in `README.md` and `01-SUMMARY.md`.

---
*Phase: 01-typed-capture-spine · Plan 04 · Completed 2026-06-27*
