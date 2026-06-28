# Nameless — Control Plane (Phase 1: Typed Capture Spine)

This is the Rust control plane for **Nameless**, a local-first, audio-native music composition
system. Phase 1 delivers the **typed capture spine**: capture an audio fragment with an intent
note into a project, store the audio immutably by content hash, persist a typed fragment whose
state machine structurally refuses to place unanalyzed work, enqueue downstream feature-extraction
work, and list it back — all compact-by-default (IDs and summaries, never audio bytes).

> **Build mode — course / learning project (read this first).** The dev machine this was authored
> on has ~4GB RAM, no Docker, and **no Rust toolchain**, so this code was **written and reviewed
> but never compiled or run here**. It is complete, idiomatic, end-to-end Rust intended to compile
> and run once you install `rustup`. The `--local` slice is designed to be RAM-safe (lean
> dependency tree, no async/DB) so it builds within 4GB; the `postgres`-feature build and all live
> Postgres/S3 work are **env-gated** (commands below). See `.planning/ENGINEERING-PRINCIPLES.md`.

## Workspace layout

```
Cargo.toml                      workspace root (3 crates)
rust-toolchain.toml             pinned stable toolchain
migrations/0001_init.sql        Postgres schema (projects, fragments, enum types) — postgres path
.env.example                    server-profile env vars (DATABASE_URL, NAMELESS_STORAGE_*)
crates/
  nameless-core/                PURE domain — no async/DB/codec deps
    fragment.rs                 Fragment/Project model, FragmentId/ProjectId, FragmentKind
    provenance.rs               Provenance (human_recorded|ai_generated|derived|sampled)
    state_machine.rs            FragmentState/Transition + the single checked transition()
    ports.rs                    ObjectStore + FragmentRepo traits (the seam)
    job.rs                      JobEnvelope + JobQueue trait + RetryPolicy
    error.rs                    typed StoreError/RepoError/JobError
  nameless-adapters/            concrete adapters behind the ports
    object_store_fs.rs          FilesystemObjectStore + content_hash()  (default)
    object_store_mem.rs         InMemoryObjectStore                     (default, tests)
    repo_mem.rs                 InMemoryFragmentRepo                    (default, tests)
    repo_file.rs                FileFragmentRepo (JSON, --local)        (default)
    probe.rs                    symphonia duration/sample_rate probe    (default)
    queue_mem.rs                InMemoryJobQueue (retry/backpressure)   (default)
    repo_pg.rs                  PostgresFragmentRepo (sqlx)             [postgres feature]
    queue_sqlxmq.rs             SqlxmqJobQueue (durable)               [postgres feature]
    object_store_s3.rs          S3ObjectStore (R2)                     [postgres feature]
  nameless-cli/                 the `nameless` binary
    cli.rs                      clap command tree + handlers + do_capture
    profile.rs                  Plane: --local vs server (postgres) wiring
    output.rs                   compact-by-default render chokepoint
    error.rs / main.rs          error mapping + entrypoint
```

## Architecture, and why it is shaped this way

### Ports-and-adapters (the one decision everything hangs off)

Every external/heavy dependency sits behind a **trait (port)** in `nameless-core`:

- `ObjectStore` — immutable blob storage by content-hash key,
- `FragmentRepo` — persistence for projects + fragments,
- `JobQueue` — the durable work seam.

Each port has a **real adapter** *and* a **test/local fake**: `FilesystemObjectStore` ↔
`S3ObjectStore`, `FileFragmentRepo`/`InMemoryFragmentRepo` ↔ `PostgresFragmentRepo`,
`InMemoryJobQueue` ↔ `SqlxmqJobQueue`. Core logic depends only on the traits. This is what makes
verification honest on a 4GB box: the local fake and the production backend satisfy the **same
trait**, so local tests exercise the *real* control flow with only the heavy leaf swapped.

### The typed state machine enforces the invariant

`state_machine::transition(provenance, from, transition) -> Result<FragmentState, IllegalTransition>`
is the **single** function that may compute a next state, and `Fragment::apply` is the **only**
mutator of `Fragment::state`. It is one exhaustive `match`; the only wildcard maps exclusively to
the error. Consequences the compiler enforces:

- **`Place` is legal only from `Analyzed`** (human/sampled/derived) **or `Promoted`** (ai) → an
  unanalyzed fragment can never be placed (CAP-05 headline).
- **No `Generated → Placed` edge** → the eval gate (`Evaluate → Promote`) is the only path for AI
  material into an arrangement. No bypass.
- **`Rejected` is terminal.**

A 480-triple test (`Provenance × FragmentState × Transition`) checks `transition` against a
hand-written legal-edge allow-list, plus named tests for each headline invariant. The complete
lifecycle is defined now even though Phase 1 only *drives* the `Captured` entry transition — later
phases wire the workers that drive the rest; the invariant is locked cheaply on day one.

### `--local` vs the `postgres` feature (why the build stays lean)

The heavy leaf — `tokio`, `sqlx`, `sqlxmq`, the S3 client — lives behind a **non-default
`postgres` cargo feature**. The default build (and the entire `--local` skeleton) compiles
pure-sync Rust with no async runtime or DB driver, so it fits the 4GB budget. The production
backends are async internally but satisfy the **sync** ports via a thin owned-runtime `block_on`
shim contained entirely in the feature-gated adapters — the async-ness never leaks into the core
or the default build.

## Running it (commands you run in a real environment)

> None of these were run here (no toolchain). Install Rust first: <https://rustup.rs>.

### The `--local` walking skeleton (no Postgres, no Docker — RAM-safe)

```bash
# Build + test the lean default (pure Rust; designed to fit 4GB):
cargo test                         # all default-feature unit tests across the 3 crates
cargo build -p nameless-cli        # the lean `nameless` binary (--local only)

# Drive the spine end-to-end (capture → store → list), each a separate process:
cargo run -p nameless-cli -- --local project create --title "demo"
#   → prints a project UUID, e.g. 7f3a...; use it below
cargo run -p nameless-cli -- --local capture ./hook.wav --note "chorus hook, over the 2nd drop" --project <PROJECT_ID>
#   → prints: captured <FRAGMENT_ID> (enqueued <JOB_ID>)
cargo run -p nameless-cli -- --local fragments list
#   → one compact line per fragment: <id>  captured  hook  "chorus hook, ..."
cargo run -p nameless-cli -- --local fragments show <FRAGMENT_ID>
cargo run -p nameless-cli -- --local --json fragments list   # machine output

# Phase 7 — reference-track context (upload a finished song for vibe + non-melodic targets):
cargo run -p nameless-cli -- --local reference upload ./fave.wav --title "Trust" --artist "Brent Faiyaz"
#   → prints: uploaded reference <REFERENCE_ID> (enqueued <JOB_ID>)   (NOT a fragment; never cloned)
cargo run -p nameless-cli -- --local reference attach <REFERENCE_ID> --project <PROJECT_ID> --role sonic-target
cargo run -p nameless-cli -- --local reference show <REFERENCE_ID>
#   → compact vibe/target summary (genre, tempo range, LUFS, tonal balance, width, vibe) —
#     the CLAP style vector is withheld (only its dimension is shown)
```

Local state lives under `.nameless-local/` (`objects/` content-addressed blobs + `db.json` +
`references.json`); it is git-ignored. In `--local`, the reference *analysis* (vibe + targets) is
produced by the Python worker / a local analyzer shim — the Rust side stores the upload + enqueues
the `AnalyzeReference` job.

### The production (`postgres`) path — ENV-GATED (real Postgres + R2, a non-4GB machine)

```bash
# Heavy compile (tokio + sqlx + sqlxmq + S3 client) — may OOM on 4GB; use a real dev box:
cargo build --features postgres

# Apply the schema to a live Postgres 16/17 (set DATABASE_URL first; see .env.example):
cargo sqlx migrate run
# Also apply sqlxmq's own queue migrations per the sqlxmq docs (creates mq_msgs etc.).

# NOTE on sqlx compile-time-checked SQL: building with --features postgres needs either
# DATABASE_URL pointing at a migrated DB at COMPILE time, or an offline cache:
cargo sqlx prepare            # generates the .sqlx/ offline cache
SQLX_OFFLINE=true cargo build --features postgres

# Live integration tests (ignored by default):
DATABASE_URL=postgres://... cargo test -p nameless-adapters --features postgres -- --ignored
NAMELESS_STORAGE_BUCKET=... NAMELESS_STORAGE_ENDPOINT=... NAMELESS_STORAGE_ACCESS_KEY_ID=... \
  NAMELESS_STORAGE_SECRET_ACCESS_KEY=... \
  cargo test -p nameless-adapters --features postgres -- --ignored s3
```

## Supply chain (verify before first build)

These crates are pinned in `Cargo.toml` at sensible current (2026) versions but were **not**
machine-verified for legitimacy here (the Phase-1 Task-0 crates.io checkpoint was intentionally not
blocked in autonomous course mode). Before your first `cargo build`, confirm each exists, is the
expected project, and is not a typosquat on <https://crates.io>:

- **Default (lean):** `clap`, `serde`, `serde_json`, `thiserror`, `uuid`, `sha2`, `symphonia`.
- **`postgres` feature:** `tokio`, `sqlx`, `sqlxmq`, `rust-s3`.

If a pinned version does not resolve, bump it to the current release (the code targets the stable
APIs of axum-era sqlx 0.8 / clap 4 / symphonia 0.5).

## Requirement coverage (Phase 1)

| Req | What | Where |
|-----|------|-------|
| CAP-01 | Capture a fragment with an intent note into a project | `cli::do_capture`, `Fragment::new_capture` |
| CAP-02 | Immutable, by-ID (content-hash) audio storage | `ObjectStore`, `FilesystemObjectStore`, `S3ObjectStore`, `content_hash` |
| CAP-05 | Typed state machine refusing illegal transitions | `state_machine::transition`, `Fragment::apply` |
| CAP-06 | Compact-by-default CLI (IDs/summaries, never audio) | `output.rs`, the whole CLI surface |
| CAP-07 | Durable job queue (enqueue), retry + backpressure | `JobQueue`, `InMemoryJobQueue`, `SqlxmqJobQueue` |

## Requirement coverage (Phase 7 — Reference-Track Context)

| Req | What | Where (Rust control plane) |
|-----|------|----------------------------|
| REF-01 | Upload + persist a reference by ID (content-hash audio) | `cli::do_reference_upload`, `ReferenceTrack::new_upload`, `ReferenceStore` (`InMemory`/`File`/`Postgres`), migration `0003` |
| REF-02 | Non-melodic vibe + sonic targets + LLM vibe description | `ReferenceContext` (built by the Python `RestrictedReferenceAnalyzer`; Rust reads the compact summary) |
| REF-03 | **Structural** non-cloning (typed asymmetry) | `reference::ReferenceContext` (no melodic column) + `conditioning::gather_melodic_conditioning` (accepts only `&[Fragment]`; `compile_fail` doctest) |
| REF-04 | Attach a reference to a project as conditioning | `cli` `reference attach`, `ReferenceStore::attach`, `project_reference_context` link |

The Python worker plane covers REF-02 (analysis) + REF-03 (the `NonMelodicFeatures` seal) — see
`workers/README.md` and `workers/LEARNING.md` §11b.

## Deferred to later phases (explicitly out of Phase 1)

Feature extraction / embeddings / the `Captured → Analyzed` driver and real job **consumers**
(Phase 2); `analyze`/`graph` subcommands (Phase 2+); the axum HTTP API (Phase 9 UI);
reference-track context (Phase 7 — **delivered**: see the coverage table above); stems, sampling +
the attribution gate (Phase 8 — the `sampled` provenance and its human-path placement are *typed in
now*, with no behavior yet); M1 consumption of the reference conditioning bundle in generation/eval.
See `.planning/phases/01-typed-capture-spine/SKELETON.md`.
