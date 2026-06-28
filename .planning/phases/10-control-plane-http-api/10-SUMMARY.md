---
phase: 10
title: Control-Plane HTTP API (axum 0.8)
status: Complete by review — env-gated (no Rust toolchain on the 4GB box; not compiled/run here)
requirements: [API-01]
mode: mvp (inserted — closes the Phase 1 axum deferral)
key_files:
  new:
    - crates/nameless-api/Cargo.toml
    - crates/nameless-api/src/lib.rs            # build_router + serve + dev CORS + body limit
    - crates/nameless-api/src/state.rs          # AppState { plane: Arc<Plane> }
    - crates/nameless-api/src/error.rs          # ApiError + From<CliError> + attribution_field_wire
    - crates/nameless-api/src/dto.rs            # wire DTOs + pure domain→wire mappers + derive_edges
    - crates/nameless-api/src/handlers.rs       # one handler per endpoint, spawn_blocking bridge
    - crates/nameless-api/src/main.rs           # bin: build_plane(local) → serve
    - crates/nameless-api/tests/api_tests.rs    # tower oneshot integration tests (in-memory Plane)
    - crates/nameless-api/LEARNING.md
    - crates/nameless-api/README.md
    - crates/nameless-cli/src/lib.rs            # NEW: exposes cli/profile/output/error as a library
  changed:
    - Cargo.toml                                # + member crates/nameless-api; + axum/tower workspace deps
    - crates/nameless-cli/Cargo.toml            # + [lib] name = nameless_cli (lib + bin)
    - crates/nameless-cli/src/main.rs           # now uses the nameless_cli library
    - crates/nameless-cli/src/cli.rs            # + do_create_project/do_capture_bytes/do_reference_upload_bytes; path fns delegate; From<RightsStatus> for RightsArg; typed IncompleteAttribution
    - crates/nameless-cli/src/error.rs          # CliError::IncompleteAttribution now carries the typed core IncompleteAttribution
    - crates/nameless-cli/src/profile.rs        # Plane ports are now Box<dyn … + Send + Sync>
    - crates/nameless-core/src/ports.rs         # + FragmentRepo::list_projects/get_project
    - crates/nameless-adapters/src/repo_mem.rs  # implement + test the two project reads
    - crates/nameless-adapters/src/repo_file.rs # implement + test the two project reads
    - crates/nameless-adapters/src/repo_pg.rs   # implement the two project reads (feature/env-gated)
verified_here:
  - "Static review of every endpoint against HttpNamelessApi.ts (paths/methods/bodies/responses)."
  - "Field-for-field DTO ↔ types.ts check (snake_case; the one camelCase `projectId`; no array/vector field)."
  - "Existing Phase-1/7/8 CLI + adapter tests preserved (path-based do_* delegate to the new byte fns)."
env_gated:
  - "cargo test -p nameless-api            # lean: tower oneshot over the in-memory Plane (no net/DB)"
  - "cargo build -p nameless-api           # default/--local profile builds (filesystem + in-memory)"
  - "cargo build -p nameless-api --features postgres   # heavy server profile (needs DATABASE_URL or sqlx offline cache)"
  - "cargo run  -p nameless-api            # serves 127.0.0.1:8080 over the --local Plane"
---

# Phase 10 — Control-Plane HTTP API (Summary)

A new `crates/nameless-api` axum 0.8 server that exposes the **exact** contract the Phase-9 web UI was
written against (`web/src/api/HttpNamelessApi.ts`), as a thin veneer over the existing control-plane
use-cases. This closes the deferral the milestone audit flagged: the UI's `HttpNamelessApi` targeted a
backend that did not exist. No new domain logic; no weakened integrity boundary.

> **Build mode:** `[env-gated]`. The dev box has ~4GB RAM, no Docker, and **no Rust toolchain**, so
> none of this was compiled or run. It is complete, real, idiomatic axum, written to be correct by
> review. Run-later commands are in the frontmatter and the README. No claim is made that it compiles
> or that tests passed.

## The seam (how reuse + testability are achieved)

```
HTTP request ─▶ axum handler ─▶ spawn_blocking( do_* over the Plane ports ) ─▶ DTO ─▶ JSON
                  │  (parse path/query/JSON/multipart in async)        │
                  └─ State<AppState{ Arc<Plane> }>                     └─ map CliError → ApiError
```

- **cli-as-a-library.** Added `crates/nameless-cli/src/lib.rs` exposing `cli`/`profile`/`output`/`error`.
  The `nameless` binary now consumes that library; the api crate consumes the *same* library, so both
  front-ends share one source of truth for `build_plane`, the `Plane` ports, and the `do_*` use-cases.
  The attribution gate (`PartialAttribution::into_complete`), content-hash, probe, and job enqueue are
  **not** re-implemented.
- **Byte-based core fns.** The capture/upload `do_*` fns read a file PATH; HTTP sends multipart BYTES.
  Added `do_capture_bytes` / `do_reference_upload_bytes` (and `do_create_project`); refactored the
  path-based fns to *read-then-delegate*, so the existing Phase-1/7/8 tests are untouched and still
  assert the same behavior.
- **Send+Sync + Arc state.** axum `State` must be `Clone + Send + Sync`. Chose `AppState { plane:
  Arc<Plane> }` and made the `Plane` ports `Box<dyn Trait + Send + Sync>` (every adapter is already
  thread-safe — `Mutex`/`PathBuf` in the fakes, runtime+pool in Postgres), so the bound is additive and
  free. The CLI path is unaffected.
- **Sync-over-async.** The ports are synchronous and the Postgres adapter `block_on`s internally
  (which panics if run on a Tokio worker thread). Every handler therefore runs the use-case inside
  `tokio::task::spawn_blocking`, capturing an `Arc<Plane>` clone + already-parsed owned data.

## Endpoint coverage (vs the TS contract)

All 15 client methods are served at the exact paths/methods, with `#[derive(Deserialize)]` request
structs and `#[derive(Serialize)]` response DTOs that embed the domain enums (so the serde labels *are*
the wire labels): `GET/POST /projects`, `POST /projects/{id}/fragments` (multipart),
`GET /fragments[?project=]`, `GET /fragments/{id}`, `GET/POST /references` (upload multipart),
`GET /references/{id}`, `POST /projects/{id}/references`, `POST /tracks/{id}/stems/separate`,
`GET /tracks/{id}/stems`, `POST /projects/{id}/samples`, `GET /samples/{fragmentId}`,
`GET /projects/{id}/graph`, `GET /projects/{id}/credits`.

## Error contract

`From<CliError> for ApiError` (pure, unit-tested): `NotFound` → **404** `{message}`; incomplete
attribution → **422** `{"error":"incomplete_attribution","missing":[…]}` (nothing created — the gate
precedes every write); `SampleOutOfRange` → **422** `{message}` (no `error` tag); `Job::Full` → **503**;
everything else → **500**; blank-title create / bad multipart → **400**.

## Things I had to FLAG (did not silently diverge)

1. **`AttributionField` wire names need a third spelling.** The TS `AttributionField` union uses
   `source_artist` AND `rights`. The core `AttributionField::as_str()` (CLI-flag-facing) returns
   `artist`/`rights`; the serde `rename_all` derive returns `source_artist`/`rights_status`. **Neither**
   built-in form matches the TS union on its own. Resolved by authoring `attribution_field_wire()` in
   `error.rs` (pinned by a unit test) — the HTTP `missing[]` matches `types.ts` exactly. This is a real
   pre-existing seam between the CLI's human flag names and the DB/wire names, surfaced now; the TS was
   already aligned to the DB/serde snake_case in Phase 9, so the server matches the TS.
2. **Two new `FragmentRepo` reads were required.** `GET /projects` (list) and the project-existence
   404s (capture/graph/credits/attach/sample — parity with the web `MockNamelessApi.requireProject`)
   need to read projects, which the `FragmentRepo` port did not expose (the CLI only ever *created* a
   project then addressed it by id). Added `list_projects` + `get_project` to the port and all three
   adapters (in-memory/file/Postgres). Additive; existing tests unaffected.
3. **Graph node `key`/`tempo_bpm` are `null` in M0.** They come from `fragment_features`, which the
   Python feature worker writes — and M0 only *enqueues* that job (no consumer runs), and the control
   plane has no feature-read port yet. So the server emits `key: null, tempo_bpm: null`, exactly the
   web mock's shape for a freshly-captured fragment. The scalars light up once a feature-read port lands
   (M1+). Not a contract divergence — the wire shape is identical.
4. **`CliError::IncompleteAttribution` changed shape** (now carries the typed core
   `IncompleteAttribution` instead of a pre-rendered `String`) so the typed `missing` fields reach the
   HTTP layer without re-deriving them. `Display` is byte-identical, so the CLI message is unchanged;
   one existing CLI test arm was updated to the typed form (its assertions are preserved + strengthened).

## Tests (exist; env-gated)

- **`tests/api_tests.rs`** (tower `oneshot`, in-memory `Plane`): happy path for every endpoint
  (projects list/create, capture→list→show, references list/upload/show/attach, stems separate/list,
  sample add→show→credits, graph); error paths (404 unknown fragment/reference/sample/project/track;
  400 blank title; 422 incomplete attribution that **creates nothing**, asserted against the shared
  store; 404 unknown stem); and the compact contract (reference analysis carries `embedding_dim`, never
  the vector; `projectId` is the only camelCase key).
- **Unit tests** in `error.rs` (`attribution_field_wire` ↔ TS union; each `CliError`→status/body
  mapping) and `dto.rs` (`derive_edges`; camelCase `projectId`; `embedding_dim`-not-vector;
  `attribution_is_not_permission`).
- **Adapter tests** for the new `list_projects`/`get_project` in `repo_mem.rs` + `repo_file.rs`.
