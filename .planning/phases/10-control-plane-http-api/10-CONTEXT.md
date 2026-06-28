# Phase 10 — Control-Plane HTTP API (CONTEXT)

> Inserted 2026-06-28 to close the axum deferral the milestone review/handoff flagged: the Phase 9
> web UI ships an `HttpNamelessApi` that targets a backend which did not exist. Only the `nameless`
> CLI exposed the control plane. This phase builds the HTTP server the UI was written against.

## What this delivers

A new `crates/nameless-api` axum 0.8 server that exposes the **exact** contract in
`web/src/api/NamelessApi.ts` + `web/src/api/HttpNamelessApi.ts`, as a thin veneer over the existing
control-plane use-cases. No new domain logic; no weakening of the integrity boundaries.

## The contract (authoritative — mirror it field-for-field)

- Endpoints/methods/paths: see `HttpNamelessApi.ts` (e.g. `GET /projects`, `POST /projects`,
  `POST /projects/:id/fragments` multipart, `GET /fragments?project=:id`, `GET /fragments/:id`,
  `GET /references`, `POST /references` multipart, `GET /references/:id`, `POST /projects/:id/references`,
  `POST /tracks/:id/stems/separate`, `GET /tracks/:id/stems`, `POST /projects/:id/samples`,
  `GET /samples/:fragmentId`, `GET /projects/:id/graph`, `GET /projects/:id/credits`).
- Request/response JSON shapes: `web/src/api/types.ts` — **snake_case**, compact (ids/labels/scalars/
  `embedding_dim` count; NEVER a waveform/feature array/vector). The Rust `output.rs` already emits these.
- Error mapping the client `parse()` expects: `404` → not-found; `422` with body
  `{"error":"incomplete_attribution","missing":[<AttributionField>...]}` for an incomplete sample
  (and create nothing); otherwise `{"message": "..."}` with a sensible status.

## Reuse, do not reinvent (testability law)

- `Plane`, `build_plane`, and `do_capture`/`do_reference_upload`/`do_stems_separate`/`do_sample_add`
  live in `nameless-cli`. The integrity gate (`PartialAttribution::into_complete`), `Fragment::new_*`,
  `content_hash`, `probe` live in `nameless-core`/`nameless-adapters`. REUSE them.
- The capture/upload `do_*` fns currently take a file PATH (they `fs::read`). HTTP sends multipart
  BYTES. Add small byte-based core fns (e.g. `do_capture_bytes(&Plane, project, kind, note, bytes)`)
  and refactor the path-based fns to read-then-delegate — additive, preserves the existing Phase-1/7/8
  tests. Expose the cli crate as a library (`src/lib.rs` re-exporting the existing modules) so the api
  crate can depend on it; keep `main.rs` working.
- Map domain → the wire DTOs using (or matching exactly) the `output.rs` view-models.

## Constraints

- **Course-mode**: complete, idiomatic axum 0.8 + tokio, with tests that EXIST. The 4GB/no-Rust box
  CANNOT compile it — everything here is `[env-gated]` (run later: `cargo test -p nameless-api`,
  `cargo build -p nameless-api`). Never claim it compiles/runs.
- **Lean-build law**: the heavy server profile (Postgres/S3/sqlxmq) stays behind `--features postgres`.
  The api crate's own axum/tokio deps are fine in the default build, but wiring the **server** `Plane`
  must remain feature-gated; `--local` (filesystem + in-memory) must build + serve without Postgres.
- **Testability**: handlers behind the `Plane` ports; test via `tower::ServiceExt::oneshot` against an
  in-memory `Plane`. No real network/DB in tests.
- Ship a `LEARNING.md` (axum/tower request lifecycle, extractors, multipart, `State`, error→Response,
  the ports-over-HTTP seam).

## Out of scope

- Auth/CORS hardening beyond a sane permissive dev default (note it as a follow-up).
- Streaming/range audio responses (the contract addresses audio by URI only; bytes never enter JSON).
- Changing the TS client (Phase 9 already aligned it to snake_case). If a mismatch is found, FLAG it —
  do not silently diverge from the committed TS contract.
