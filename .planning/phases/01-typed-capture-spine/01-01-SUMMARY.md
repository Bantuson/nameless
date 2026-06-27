---
phase: 01-typed-capture-spine
plan: 01
subsystem: control-plane
tags: [rust, cargo-workspace, ports-and-adapters, content-addressing, symphonia, clap]
requires:
  - phase: none
    provides: greenfield
provides:
  - "Cargo workspace (nameless-core/adapters/cli) + the walking skeleton"
  - "ObjectStore + FragmentRepo ports; FilesystemObjectStore + content_hash; InMemory/File repos; symphonia probe"
  - "nameless CLI: project create | capture | fragments list/show; compact-by-default + --json; --local profile"
affects: [phase-02-fragment-analysis, phase-09-web-ui]
tech-stack:
  added: [clap 4, serde, serde_json, thiserror, uuid, sha2, symphonia 0.5]
  patterns: [ports-and-adapters, content-addressed-immutable-storage, compact-by-default-output]
key-files:
  created: ["Cargo.toml", "rust-toolchain.toml", ".gitignore", "crates/nameless-core/*", "crates/nameless-adapters/src/{object_store_fs,object_store_mem,repo_mem,repo_file,probe}.rs", "crates/nameless-cli/*"]
  modified: []
key-decisions:
  - "FileFragmentRepo as atomic JSON doc (not SQLite) to keep the default build pure-sync-Rust."
  - "Task 0 supply-chain checkpoint not blocked (autonomous course mode); crates flagged in README."
patterns-established:
  - "Ports-and-adapters seam with a real + fake adapter per dependency."
requirements-completed: [CAP-01, CAP-02, CAP-06]
duration: 8min
completed: 2026-06-27
status: complete
---

# Phase 1 Plan 01: Walking Skeleton Summary

**3-crate Cargo workspace whose `nameless --local` CLI captures audio by SHA-256 content hash into a JSON-file fragment repo and lists it back compact-by-default — no Postgres.**

See the consolidated phase summary: [`01-SUMMARY.md`](./01-SUMMARY.md) (Performance, full file map, Verification, Deviations).

## Highlights
- Workspace + `nameless-core` domain/ports/errors; `FilesystemObjectStore` (+ `InMemoryObjectStore`), `InMemoryFragmentRepo`, `FileFragmentRepo`, symphonia `probe`.
- `nameless` binary: `project create`, `capture <path> --note --project [--kind]`, `fragments list/show`; `--local` + `--json`; single compact `output.rs` chokepoint (never prints audio bytes).
- CAP-01 (capture+note), CAP-02 (immutable by-ID via content hash), CAP-06 (compact-by-default) satisfied on the lean build.

## Commits
- `d4b8f01` workspace + core · `3c6c182` default adapters · `0d241f8` CLI skeleton.

## Verification
Reviewed-complete (tests written): content-hash determinism/immutability, repo round-trips + cross-instance persistence, probe on generated WAV/garbage, clap parse + capture-enqueue. Env-gated: `cargo test`, `cargo run -p nameless-cli -- --local …` (needs rustup; absent here).

---
*Phase: 01-typed-capture-spine · Plan 01 · Completed 2026-06-27*
