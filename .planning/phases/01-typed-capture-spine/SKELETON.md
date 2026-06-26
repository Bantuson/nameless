# Walking Skeleton — Nameless

**Phase:** 1 (Typed Capture Spine)
**Generated:** 2026-06-26

## Capability Proven End-to-End

> The smallest user-visible capability that exercises the full spine.

A solo producer can run, on the 4GB dev machine with **no Postgres and no Docker**:

```
nameless --local project create --title "demo"
nameless --local capture ./hook.wav --note "chorus hook, over the 2nd drop" --project <PROJECT_ID>
nameless --local fragments list
nameless --local fragments show <FRAGMENT_ID>
```

…and see the captured fragment listed by ID — its raw audio stored immutably by content hash, its intent note attached, its state `captured` — with the CLI printing only IDs and compact summaries, never audio bytes or feature arrays. That single capture→store→list loop is the spine; everything else in M0/M1 hangs off it.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / control plane | Rust, Cargo **workspace** (`nameless-core`, `nameless-adapters`, `nameless-cli`) | PRD §5: the hard part is schema integrity + exhaustive state transitions + gate enforcement — Rust's strength. Workspace isolates the heavy backend leaf from the lean domain. |
| Architecture style | **Ports-and-adapters** (`ObjectStore`, `FragmentRepo`, `JobQueue` traits) | The single decision that makes RAM-safe verification honest: prod (S3/R2, Postgres, sqlxmq) and the local fake satisfy the same trait, so local tests exercise real control flow with only the heavy leaf swapped (ENVIRONMENT.md). |
| State model | One typed `FragmentState` enum + a single exhaustive `transition()` → `Result<_, IllegalTransition>` | PRD §7 / CONTEXT: "cannot place unanalyzed" is enforced by the compiler's exhaustive match, not by convention. The harness gates; the agent explores. |
| Object storage | Immutable, addressed by **SHA-256 content hash**; `FilesystemObjectStore` fake + `S3ObjectStore` (R2) prod | CAP-02: de-duplicating, immutable, never mutated. Filesystem fake is the local stand-in; R2 (no egress) is prod. Audio never enters agent context — referenced by `audio_uri` only. |
| Audio probing | **symphonia** (pure Rust) | CONTEXT: no ffmpeg/native dependency → keeps the 4GB box buildable; accepts wav/mp3/flac/m4a; stores original bytes regardless of probe success. |
| Local persistence | `--local` profile: `FilesystemObjectStore` + `FileFragmentRepo` (serde_json file) + `InMemoryJobQueue` | Runs the whole capture loop with NO Postgres on 4GB (CONTEXT success-criterion #1). JSON file chosen over SQLite to keep the default compile pure-Rust + minimal. |
| Job queue | `JobQueue` trait; `InMemoryJobQueue` (tests) + `SqlxmqJobQueue` (Postgres, prod) | CAP-07 / STACK §5: durable Postgres-backed queue at solo scale — **defer NATS/Redis entirely**. Phase 1 enqueues only. |
| Heavy-dep isolation | tokio + sqlx 0.8.6 + sqlxmq + S3 client live behind a **non-default `postgres` feature** | The default `cargo build` (and the whole `--local` skeleton) compiles lean — no async/DB tree — so it does not OOM on 4GB. The heavy feature compile + live-service tests are env-gated to the user's real environment. |
| HTTP API (axum) | **Deferred** (not in Phase 1) | CONTEXT deferred: the M0 capture loop is CLI-first; axum lands when a phase needs it (UI is Phase 9). Dropping axum keeps the Phase 1 dependency surface minimal. |
| Directory layout | `crates/{nameless-core,nameless-adapters,nameless-cli}` + `migrations/` | Mirrors ARCHITECTURE.md's additive control-plane shape; later phases (2/7/8) extend the schema + adapters, not the spine. |

## Stack Touched in Phase 1

- [x] Project scaffold — Cargo workspace, `rust-toolchain.toml`, lean default features (Plan 01)
- [x] Routing — N/A (CLI-first; axum deferred). CLI command tree is the surface: `project`, `capture`, `fragments` (Plan 01)
- [x] Database — at least one real read AND one real write: `--local` `FileFragmentRepo` write (capture) + read (list/show) end-to-end; prod `PostgresFragmentRepo` behind the feature (Plans 01, 04)
- [x] UI / interactive element — `nameless capture` then `nameless fragments list` wired to the storage seam (Plan 01)
- [x] Deployment — documented local full-stack run: `cargo run -p nameless-cli -- --local …` (no Postgres). Heavy/prod path env-gated (Plan 04)

> **Env-honesty note:** rustc/cargo are ABSENT on the dev machine. "Touched" means real, reviewed code is written; the `--local` slice is designed RAM-safe so it compiles + runs within 4GB once `rustup` is installed. The `postgres`-feature compile and all live Postgres/S3 tests are env-gated (see each plan's `verification_classes.env_gated`).

## Out of Scope (Deferred to Later Slices)

> Explicit — prevents future phases re-litigating Phase 1's minimalism.

- Feature extraction (f0/chroma/onsets/key/LUFS), embeddings, pgvector indexing, and the actual `Captured → Analyzed` transition driver — **Phase 2** (CAP-03, CAP-04).
- Real job **consumers** / the feature worker — Phase 2 (Phase 1 enqueues only).
- `nameless analyze` and `nameless graph` subcommands — Phase 2+.
- The axum HTTP API surface — introduced when a phase needs it (Phase 9 UI).
- Reference-track context, stems, sampling, attribution gate, credits — Phases 7-8 (the `sampled` provenance + state path are *typed in now*, but no behavior).
- Generation, eval gate, mix/master — M1.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2 — Fragment Analysis:** the feature worker consumes `FeatureExtract` off the queue, writes `fragment_features` + embeddings (pgvector), drives `Captured → Analyzing → Analyzed`; adds `nameless analyze`/`graph` + similarity retrieval.
- **Phase 7 — Reference-Track Context:** `reference_tracks` / `reference_context` tables (no melody/chroma column — non-cloning is structural); reuses the `ObjectStore` + worker seam.
- **Phase 8 — Stem Library + Attributed Sampling:** promote a stem to a `sampled` fragment; the state machine gains the attribution-completeness invariant on `Place` (extends, doesn't replace, this phase's `transition()`).
- **Phase 9 — Thin Web UI:** axum surface + React, sitting on the same control plane + CLI.
