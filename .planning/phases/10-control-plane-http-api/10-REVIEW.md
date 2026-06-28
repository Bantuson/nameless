---
status: issues
phase: 10-control-plane-http-api
depth: deep
files_reviewed: 19
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
---

# Phase 10: Control-Plane HTTP API — Code Review

**Depth:** deep (cross-file: router ↔ handlers ↔ dto ↔ error ↔ ports ↔ adapters, plus per-endpoint contract diff against the Phase-9 web client)
**Verdict — CONTRACT PARITY: CLEAN.** All 15 endpoints match `HttpNamelessApi.ts` exactly: path (axum 0.8 `{id}` capture), method, request-body field names (snake_case), and response JSON shapes vs `types.ts` (field names, types, nullability, enum labels). The `projectId` camelCase exception, `attribution_is_not_permission: true`, `embedding_dim`-without-vector, the `{"error":"incomplete_attribution","missing":[…]}` 422 body, and the `attribution_field_wire()` strings all match the TS unions field-for-field. The attribution gate, compact/non-cloning contract, and sampled lifecycle are preserved by the HTTP layer (the gate runs in the reused `do_*`, before any write). `spawn_blocking` usage is correct: every DB-touching handler captures owned/`Arc` data and runs the sync use-case off the async worker threads; no `block_on` on an async worker, no Mutex-across-await.

The findings below are robustness/security/parity-edge items, not contract breaks.

## Critical Issues

None found.

## Warnings

### WR-01: File-backed `--local` adapters lose writes under the now-concurrent HTTP server (data loss)

**File:** `crates/nameless-adapters/src/repo_file.rs:74-139` (also `FileReferenceStore`, `FileSampleStore`); reached via `crates/nameless-cli/src/profile.rs:59-79` and `crates/nameless-api/src/main.rs:22-23` (default = local profile).
**Issue:** `FileFragmentRepo` performs a non-atomic read-modify-write per mutation (`load()` → mutate `Vec` → `store()`), with **no cross-call lock** (the struct is just `{ path: PathBuf }`). Until Phase 10 this was safe because the `nameless` CLI is one-process-one-operation. The axum server is multi-threaded (`rt-multi-thread`) and dispatches each write through `spawn_blocking`, so two concurrent `POST`s (e.g. the web UI firing parallel captures, or a double-submit) can both `load()` the same `db.json`, each append a different row, and each `store()` — the second atomic rename overwrites the first, **silently dropping a fragment / reference / sample**. The atomic temp-file+rename prevents file corruption but not lost updates. The default `nameless-api` build serves exactly this profile. (`InMemory*` adapters are safe — they lock a `Mutex` per op; Postgres is safe — single statements. Only the file profile races.)
**Why it matters:** Captured musical material or a sampled-fragment attribution can vanish with no error returned to the client — a data-loss class defect, newly reachable because Phase 10 puts a concurrent front-end over a serial-assumption store.
**Fix:** Serialize file writes. Cheapest: wrap the on-disk state in a process-wide `Mutex` inside each file adapter (hold it across the load→store cycle), or front the local profile with a single write-worker. Alternatively, document and enforce single-flight at the API layer for the `--local` profile. [env-gated to reproduce live, but the race is provable by reading: no lock spans `load()`/`store()`.]

### WR-02: Wildcard CORS + no authentication on a state-mutating local control plane

**File:** `crates/nameless-api/src/lib.rs:100-121` (`cors_dev`), applied in `build_router` at `:90`.
**Issue:** Every response is stamped `Access-Control-Allow-Origin: *` and the API has no auth on any route, including the mutating `POST /projects`, `/fragments`, `/samples`, `/references`. The server binds `127.0.0.1:8080` by default, but `*` CORS means any website the user visits while the server runs can issue cross-origin reads/writes to their local control plane (CSRF / DNS-rebinding-style). Because there are no credentials/cookies, `*` is technically valid, but combined with zero auth it lets an arbitrary page drive the user's local Nameless data.
**Why it matters:** Low-likelihood but real for a local-first tool; a visited page could enumerate/create/sample fragments.
**Fix:** This is explicitly documented as a dev-only default with a hardening follow-up (lib.rs:88-99), so it is acknowledged scope — but track it: pin the allowed origin to the Vite dev origin (not `*`), and gate non-`OPTIONS` mutations behind a local token/`Origin` check before any non-local exposure. Keep as a release blocker for any non-localhost deployment.

## Info

### IN-01: Capture validates empty note (400) before the project-existence check (404)

**File:** `crates/nameless-api/src/handlers.rs:150-159`
**Issue:** `read_capture_multipart` is awaited and `form.note.trim().is_empty()` → 400 runs *before* the `get_project … is_none()` → 404 inside `run_blocking`. So a capture into an unknown project with an empty note returns 400, not the 404 the mock's `requireProject` would give; and the entire file is buffered into memory before the project check. Minor ordering/parity edge, not a contract break for valid requests.
**Fix:** If strict parity matters, move the project-existence 404 ahead of body validation (or do a cheap pre-read project check). Otherwise leave as-is; harmless for well-formed clients.

### IN-02: Graph nodes always emit `key`/`tempo_bpm` = null, even for analyzed fragments

**File:** `crates/nameless-api/src/dto.rs:363-383` (`FragmentNodeDto::from_domain`)
**Issue:** `key`/`tempo_bpm` are hardcoded `None` because M0 has no feature-read port. This matches the mock for a *freshly-captured* fragment but diverges from a mock that surfaces key/tempo once analyzed. Documented in-code and in `10-VERIFICATION.md`. Wire shape is correct (`string | null`, `number | null`); only the value lights up later (M1+).
**Fix:** None for M0. Land a `fragment_features` read port in M1 so analyzed nodes carry the scalars.

### IN-03: `create_project` returns 200 OK rather than 201 Created

**File:** `crates/nameless-api/src/handlers.rs:76-91`
**Issue:** A resource-creating POST returns 200. The client only checks `res.ok`, so this is harmless and not a contract violation; noted for REST hygiene.
**Fix:** Optional — return `(StatusCode::CREATED, Json(dto))`.

### IN-04: Server profile constructs multiple independent Tokio runtimes

**File:** `crates/nameless-cli/src/profile.rs:83-110` (each `connect` → `Runtime::new()` in `crates/nameless-adapters/src/repo_pg.rs:46-57`)
**Issue:** `server_plane()` builds the repo, queue, store, references, and samples via separate `connect()` calls, each spinning up its own multi-thread runtime + pool, even though `PostgresFragmentRepo::new(rt, pool)`/`runtime()` exist precisely to share one runtime. Pre-existing (predates Phase 10) and behind the `postgres` feature (env-gated, never compiled here), so not a Phase-10 regression — flagged for the eventual server bring-up.
**Fix:** Build one `Arc<Runtime>` + pool and thread it through the sibling adapters via the existing shared constructors.

---

_Reviewer: Claude (gsd-code-reviewer) — deep depth. Rust crate is complete-but-uncompiled (course box); findings are by reading. Items needing a live compile/run to confirm are tagged [env-gated]._
