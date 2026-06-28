# nameless-api

The Nameless **control-plane HTTP API** — an [axum](https://github.com/tokio-rs/axum) 0.8 server that
exposes the exact contract the web UI's `HttpNamelessApi` (`web/src/api/HttpNamelessApi.ts`) was
written against. It is a thin veneer over the `nameless-cli` control-plane use-cases: no new domain
logic, no weakened integrity boundary (the attribution gate, content-hashing, probing, and job
enqueue all stay in the reused `do_*` functions).

> **`[env-gated]`** — the 4GB course box has no Rust toolchain, so this crate is **not compiled or run
> here**. It is complete, real, idiomatic axum and is written to be correct by review. Use the
> run-later commands below on a real dev machine. Nothing in this repo claims it compiles or that its
> tests passed.

## Endpoints (mirror `HttpNamelessApi.ts` exactly)

| Method & path | Use-case |
|---|---|
| `GET /projects` | list projects (newest-first) |
| `POST /projects` | create a project (`{ "title": "…" }`) |
| `POST /projects/{id}/fragments` | capture a fragment (multipart: `file`, `note`, `kind`) |
| `GET /fragments?project={id}` | list fragments (optionally scoped to a project) |
| `GET /fragments/{id}` | fragment detail |
| `GET /references` | list reference tracks |
| `POST /references` | upload a reference (multipart: `file`, optional `title`/`artist`) |
| `GET /references/{id}` | reference vibe/target summary (analysis null until analyzed) |
| `POST /projects/{id}/references` | attach a reference (`{ "reference_id", "role" }`) |
| `POST /tracks/{id}/stems/separate` | enqueue stem separation |
| `GET /tracks/{id}/stems` | list a track's retained stems |
| `POST /projects/{id}/samples` | promote a stem to a `sampled` fragment (the attribution gate) |
| `GET /samples/{fragmentId}` | a sample's attribution + rights status |
| `GET /projects/{id}/graph` | the fragment graph (nodes + lineage edges) |
| `GET /projects/{id}/credits` | the project's sample credits sheet |

Request/response JSON is **snake_case** and **compact** (ids/labels/scalars + `embedding_dim` count —
never a waveform, feature array, or embedding vector). The one camelCase exception, matching the TS
`ProjectGraph` type, is `projectId` on `GET /projects/{id}/graph`.

### Error contract

- `404` → `{ "message": "…" }` (the client maps any 404 to `NotFoundError`).
- `422` + `{ "error": "incomplete_attribution", "missing": [<AttributionField>…] }` → an incomplete
  sample. **Nothing is created** (the gate runs before any write). `missing` uses the TS
  `AttributionField` spellings (`source_artist`, `rights`, …).
- everything else → `{ "message": "…" }` with a sensible status (`400` bad input, `503` queue
  backpressure, `500` otherwise).

## Run later (env-gated commands)

```bash
# Lean tests — in-memory Plane, no DB/socket/worker (the default, RAM-safe path):
cargo test -p nameless-api

# Build the default (lean, --local) server — filesystem + in-memory adapters, no Postgres:
cargo build -p nameless-api

# Build with the heavy server profile (Postgres + sqlxmq + S3/R2). Needs a migrated DB reachable at
# DATABASE_URL, or an sqlx offline cache (SQLX_OFFLINE=true + a prepared `.sqlx/`):
cargo build -p nameless-api --features postgres

# Run the server (defaults to the lean --local profile, binds 127.0.0.1:8080):
cargo run -p nameless-api
#   NAMELESS_API_ADDR=0.0.0.0:9000 cargo run -p nameless-api      # custom bind address
#   cargo run -p nameless-api --features postgres -- --server     # Postgres/S3 profile
```

## Point the web UI at it

The UI defaults to the in-memory `MockNamelessApi`. To talk to this server instead, set (see
`web/.env.example`):

```bash
VITE_NAMELESS_CLIENT=http
VITE_API_BASE_URL=http://127.0.0.1:8080
```

then run the Vite dev server. Everything above the `NamelessApi` port (hooks, screens) is unchanged —
swapping the real backend in is a one-line composition-root change (`web/src/api/createClient.ts`).

## Profiles

- **default / `--local`** (this build): `FilesystemObjectStore` + `FileFragmentRepo`/reference/sample
  JSON stores + `InMemoryJobQueue`, all under `.nameless-local/`. No Postgres, no network — buildable
  and servable on a modest machine.
- **`--features postgres` + `--server`**: `PostgresFragmentRepo` + `SqlxmqJobQueue` + `S3ObjectStore`,
  built from env (`DATABASE_URL`, S3/R2 creds). Heavy (tokio + sqlx + S3 client).

The job queue is **enqueue-only** in M0 (no consumer runs): `separate`/`upload`/`capture`/`sample`
return an `enqueued_job` id, but the Python worker that turns those jobs into features/stems is a later
milestone. So `GET /tracks/{id}/stems` returns the stems a worker has already written, and graph nodes
carry `key: null`/`tempo_bpm: null` until a feature-read path exists (M1+).

## Security follow-ups (out of scope for this phase)

- **CORS** here is a permissive dev default (`Access-Control-Allow-Origin: *`). A real deployment must
  pin allowed origins and handle credentials.
- **AuthN/AuthZ** is absent — this is a single-user local-first control plane. Adding auth (and the
  multi-tenant story) is a follow-up.
- The body limit (64 MiB) bounds per-request memory but there is no global rate limiting yet.
