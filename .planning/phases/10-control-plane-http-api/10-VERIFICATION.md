# Phase 10 — Verification

**Phase:** 10 · Control-Plane HTTP API (axum 0.8)
**Requirement:** API-01
**Build mode:** `[env-gated]` — the dev box has no Rust toolchain; nothing here was compiled or run.
Each criterion is marked **met-by-review** (verified statically against the committed TS contract and
the reused Rust core) with the exact run-later command to confirm on a real machine. **No claim is made
that the code compiles or that any test passed.**

Run-later commands (all `[env-gated]`):

```bash
cargo test  -p nameless-api                      # lean: tower oneshot over in-memory Plane (no net/DB)
cargo build -p nameless-api                      # default/--local profile (filesystem + in-memory)
cargo build -p nameless-api --features postgres  # heavy server profile (needs DATABASE_URL / sqlx offline cache)
cargo run   -p nameless-api                      # serve 127.0.0.1:8080 over the --local Plane
cargo test  -p nameless-cli                       # confirms the cli-lib refactor + byte-fn delegation
cargo test  -p nameless-adapters                  # confirms list_projects/get_project adapters
```

---

## Success Criterion 1 — every endpoint at the exact paths/methods/shapes

> An axum router exposes every endpoint in `NamelessApi.ts`/`HttpNamelessApi.ts` … at the exact paths,
> methods, and snake_case request/response shapes the TS client sends and expects.

**Status: MET BY REVIEW.**

- `build_router` (`crates/nameless-api/src/lib.rs`) registers all 15 endpoints. Each route string was
  checked against the URL `HttpNamelessApi.ts` builds; axum 0.8 `{id}` param syntax resolves to the same
  URLs (e.g. client `/projects/<uuid>/fragments` ↔ route `/projects/{id}/fragments`).
- Request bodies are `#[derive(Deserialize)]` structs with the client's snake_case keys:
  `CreateProjectBody{title}`, `AttachReferenceBody{reference_id, role}`,
  `AddSampleBody{stem_id, source_artist, source_title?, start_ms, end_ms, rights}` — matched against the
  `HttpNamelessApi.ts` `sendJson` bodies and the `HttpNamelessApi.test.ts` wire-parity assertions.
- Response DTOs (`dto.rs`) are `#[derive(Serialize)]` and embed the domain enums, so their serde labels
  ARE the wire labels; each field was diffed against `web/src/api/types.ts`. The one camelCase exception
  (`ProjectGraph.projectId`) is pinned with `#[serde(rename = "projectId")]` and a unit test.
- Multipart (`POST /projects/{id}/fragments`, `POST /references`) extracts `file` bytes + `note`/`kind`
  / `title`/`artist` text fields.

**Confirm:** `cargo test -p nameless-api` (the integration tests exercise every endpoint).

---

## Success Criterion 2 — REUSE the `do_*` use-cases + view-models; do not re-implement the gate

> Handlers REUSE the existing `do_capture`/`do_reference_upload`/`do_stems_separate`/`do_sample_add`
> use-cases … over the `Plane` ports — the integrity logic … is NOT re-implemented or weakened.

**Status: MET BY REVIEW.**

- `crates/nameless-cli/src/lib.rs` exposes the CLI modules; the api crate depends on the cli library and
  calls `do_capture_bytes`/`do_reference_upload_bytes`/`do_stems_separate`/`do_sample_add`/
  `do_create_project` over the shared `Plane`. The byte-based fns are thin extractions the path-based
  `do_capture`/`do_reference_upload` now delegate to (read-then-delegate), so the gate, content-hash,
  probe, enqueue, and the `sample add` rollback-on-failure all live exactly once, in `cli.rs`.
- The attribution gate is untouched: `do_sample_add` still calls `PartialAttribution::into_complete`.
  The DTOs are a pure domain→wire projection of the same values `output.rs` prints.

**Confirm:** `cargo test -p nameless-cli` (the existing gate/rollback tests still pass) and
`cargo test -p nameless-api` (the `add_sample_incomplete_…_creates_nothing` test asserts the gate over
HTTP, checking the shared store has no fragment/attribution after a 422).

---

## Success Criterion 3 — the error contract matches the client's `parse()`

> 404 → not-found, 422 `{error:"incomplete_attribution", missing:[...]}` for an incomplete sample (and
> nothing is created), else `{message}` with an appropriate status.

**Status: MET BY REVIEW.**

- `From<CliError> for ApiError` (`error.rs`): `NotFound` → 404; `IncompleteAttribution` → 422 with the
  typed `missing[]` (mapped to the TS spellings via `attribution_field_wire`); `SampleOutOfRange` → 422
  `{message}` (no `error` tag, so the client treats it as a generic `ApiError`, not the attribution
  branch); `Job::Full` → 503; otherwise 500. Handlers add 400 for a blank title / malformed multipart.
- "Nothing is created" is guaranteed by the reused gate (validation precedes every write; any post-write
  failure compensates) and is asserted over HTTP by an integration test against the shared store.

**Confirm:** `cargo test -p nameless-api` — unit tests in `error.rs`
(`incomplete_attribution_maps_to_422_with_typed_missing`, `not_found_maps_to_404`,
`sample_out_of_range_maps_to_422_message_without_error_tag`, `job_full_maps_to_503`) +
integration tests (`*_is_404`, `add_sample_incomplete_attribution_is_422_and_creates_nothing`).

---

## Success Criterion 4 — testable with no network/DB; heavy profile behind `postgres`; lean build serves `--local`

> Handlers run over in-memory adapters via `tower`/`axum` test harness; the heavy server profile stays
> behind the `postgres` feature, the lean build still compiles `--local`.

**Status: MET BY REVIEW.**

- `tests/api_tests.rs` builds the real router over an in-memory `Plane` and drives it with
  `tower::ServiceExt::oneshot` — no socket, no DB, no worker. `AppState::from_arc` lets a test keep the
  `Arc<Plane>` to assert post-conditions.
- The server `Plane` (Postgres + sqlxmq + S3/R2) is reached only via `build_plane(false)`, which exists
  only under `--features postgres` (propagated `postgres = ["nameless-cli/postgres"]`). The default
  build wires `build_plane(true)` → filesystem + in-memory adapters, no tokio-sqlx/S3. `main.rs` defaults
  to `--local`; `--server` selects the heavy profile (and errors clearly without the feature).

**Confirm:** `cargo test -p nameless-api` and `cargo build -p nameless-api` (lean, no Postgres), then
`cargo build -p nameless-api --features postgres` on a machine with `DATABASE_URL`/sqlx offline cache.

---

## Success Criterion 5 — course-mode: complete idiomatic axum 0.8 + tests that EXIST + LEARNING.md

> Complete, real, idiomatic axum 0.8 code + tests that EXIST (env-gated — not compiled on the 4GB box);
> a `LEARNING.md` explaining the axum/tower request lifecycle, multipart handling, and the
> ports-over-HTTP seam.

**Status: MET BY REVIEW.**

- Complete crate: `lib.rs` (router/serve/dev-CORS/body-limit), `state.rs`, `error.rs`, `dto.rs`,
  `handlers.rs`, `main.rs`, plus `tests/api_tests.rs`. All real, idiomatic axum 0.8 (extractors, `State`,
  `Multipart`, `middleware::from_fn`, `IntoResponse`, `axum::serve`, `spawn_blocking`).
- `crates/nameless-api/LEARNING.md` covers the tower/axum request lifecycle, extractors + the
  body-extractor-last rule, multipart (borrow-vs-consume, body limit), `State`/`Arc`/Send+Sync,
  sync-over-async via `spawn_blocking`, error→`IntoResponse`, the wire-name subtlety, and the
  ports-over-HTTP seam. `README.md` has the env-gated run commands + how to point the web UI at it.

**Confirm:** `cargo test -p nameless-api` (tests exist and are meant to pass once compiled). LEARNING.md
+ README.md present in `crates/nameless-api/`.

---

## Flags carried forward (see 10-SUMMARY.md "Things I had to FLAG")

1. `attribution_field_wire()` authored because neither `as_str()` nor serde-rename matches the TS
   `AttributionField` union (`source_artist` + `rights`). Pinned by a unit test.
2. `FragmentRepo::list_projects`/`get_project` added (port + 3 adapters) to serve `GET /projects` and
   the project-existence 404s (mock parity). Additive.
3. Graph node `key`/`tempo_bpm` are `null` in M0 (no feature-read port yet) — same wire shape as the web
   mock for a freshly-captured fragment; scalars arrive in M1+.
4. `CliError::IncompleteAttribution` now carries the typed core `IncompleteAttribution` (Display
   unchanged); one CLI test arm updated to the typed form, assertions preserved + strengthened.
