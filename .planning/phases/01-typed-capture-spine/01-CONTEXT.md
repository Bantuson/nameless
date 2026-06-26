# Phase 1: Typed Capture Spine - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous; grey areas auto-resolved with recommended defaults per user "don't wait" instruction)

<domain>
## Phase Boundary

Deliver the typed capture spine of the Nameless control plane: a producer can capture an audio fragment (with an intent note) into a durable, typed fragment graph whose Rust state machine structurally refuses to place unanalyzed work, with immutable by-ID audio storage, a durable Postgres-backed job queue, and a compact-by-default `nameless` CLI.

In scope: `ObjectStore` abstraction + immutable storage, the fragment data model, the typed state machine + provenance enums, the `JobQueue` abstraction (enqueue only), and the CLI surface for project/capture/fragments.

Out of scope (later phases): feature extraction / embeddings + reaching `analyzed` (Phase 2), the knowledge pipeline (Phases 3-6), reference/sampling (Phases 7-8), the web UI (Phase 9), and any generation/eval/mix (M1).
</domain>

<decisions>
## Implementation Decisions

### Object Storage
- Define an `ObjectStore` trait (put/get/exists by key). Ship a production S3/R2 implementation (behind config) AND a filesystem-backed implementation used for local runs and tests.
- Audio is addressed by **content hash (SHA-256)** → immutable and de-duplicating; the `fragments` row carries its own UUID `id` plus `audio_uri` = the hash key. Raw bytes are stored as-is, never mutated.
- Probe duration / sample_rate with pure-Rust **`symphonia`** (no ffmpeg/native dependency — keeps the 4GB box buildable). Accept common formats (wav/mp3/flac/m4a); store original bytes regardless.
- Audio bytes and feature arrays are NEVER echoed into CLI output (compact-by-default contract starts here).

### Fragment State Machine
- Define the COMPLETE typed model now (cheap, and it locks the invariant early): `provenance = human_recorded | ai_generated | derived | sampled` (include `sampled` now per PROJECT.md, even though sampling lands in Phase 8); state enum per PRD §7 human + ai paths.
- Phase 1 only wires the `captured` entry transition; later phases wire analyzing/analyzed/placed/etc.
- The "cannot place unanalyzed" invariant is enforced by a **checked transition function with exhaustive `match`** returning `Result<_, IllegalTransition>` — illegal transitions are a typed error, enforced by the harness, not convention. (`place()` only succeeds from `Analyzed`.) Unit-tested exhaustively.
- Persistence via a `FragmentRepo` trait: a **Postgres (sqlx) impl** for production, and an **in-memory impl** for RAM-safe unit tests of the state-machine + invariants (no DB server needed).

### Job Queue
- Define a `JobQueue` trait (enqueue / consume / retry / backpressure) with a typed `JobEnvelope` enum (e.g. `FeatureExtract`, `Separate`) serialized to JSON.
- Production impl backed by **sqlxmq (Postgres)**; an **in-memory impl** exercises retry / backpressure / durability semantics in unit tests.
- Phase 1 ENQUEUES only — real consumers (feature extraction) are Phase 2. A trivial test consumer demonstrates retry/backpressure in tests.
- Defaults: max attempts ~5, exponential backoff; configurable.

### CLI (`nameless`)
- `clap` (derive). Compact-by-default human output + `--json` for machine output. Never prints audio/arrays.
- Phase 1 subcommands: `nameless project create`, `nameless capture <path> --note <text> --project <id>`, `nameless fragments list`, `nameless fragments show <id>`.
- Config via env (`DATABASE_URL`, `NAMELESS_STORAGE_*`) PLUS a **`--local` dev profile** that uses the filesystem `ObjectStore` + the in-memory/SQLite repo so the CLI runs WITHOUT Postgres — this is what makes success-criterion #1 demonstrable on the 4GB machine.

### Claude's Discretion
- Crate/workspace layout, module names, error type design (e.g. `thiserror`), and exact clap structure are at Claude's discretion, following idiomatic Rust and the PRD's "schema integrity reads as senior" intent.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — this is the first code phase (greenfield). PRD `nameless-prd.md` §4–7 is the authoritative architecture; `.planning/research/ARCHITECTURE.md` and `STACK.md` carry concrete schema/enum deltas and validated crate versions (axum 0.8, sqlx 0.8, sqlxmq, symphonia).

### Established Patterns
- To be established here: typed state machine via exhaustive match; trait-based ports (ObjectStore, FragmentRepo, JobQueue) with prod + test/in-memory adapters — the ports-and-adapters shape is what makes RAM-safe verification honest (real control flow, swapped heavy leaf).

### Integration Points
- Workspace root for the Rust control plane (e.g. `control-plane/` or a cargo workspace). The `nameless` CLI is the control plane's primary surface. Postgres schema (migrations) introduced here is extended by Phases 2/7/8.
</code_context>

<specifics>
## Specific Ideas

- **Environment constraint (authoritative): `.planning/ENVIRONMENT.md`.** ~4GB RAM, no Docker, Rust toolchain ABSENT. Verification MUST be RAM-safe: pure unit tests + in-memory adapters; do NOT force-compile the full axum+sqlx+tokio tree if it OOMs. Deliver real code; verify state-machine/queue/CLI-parse logic via `cargo test` on small units IF a toolchain installs and compiles within RAM — otherwise mark `cargo build`/Postgres integration as env-gated with the exact command for the user's real environment.
- Compact-by-default CLI output is a hard requirement (PRD token strategy) and starts in this phase.
</specifics>

<deferred>
## Deferred Ideas

- Feature extraction, embeddings, `analyzed` transition → Phase 2.
- Real job consumers / workers → Phase 2.
- `axum` HTTP API surface → not required for the CLI-first M0 capture loop; introduce when a phase needs it (UI is Phase 9, which can talk to the control plane).
- Full graph-slice query subcommands → minimal here, richer in Phase 2.
</deferred>
