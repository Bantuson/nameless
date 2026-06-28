# LEARNING — the control-plane HTTP API (axum 0.8)

This crate is a *teaching* artifact as much as a deliverable: it is the seam where the synchronous,
local-first control plane meets the asynchronous HTTP world. Read this before changing a handler.

> **Status:** `[env-gated]`. The 4GB course box has no Rust toolchain, so nothing here was compiled
> or run. It is written to be correct by review. Run later with `cargo test -p nameless-api`.

---

## 1. The request lifecycle (what actually happens to a request)

```text
TCP byte stream
   │  hyper (inside axum::serve) parses HTTP/1.1
   ▼
http::Request<Body>
   │  Router matches method + path  ("/projects/{id}/samples", POST)
   ▼
the matched MethodRouter
   │  middleware layers run outside-in:  cors_dev  →  DefaultBodyLimit
   ▼
extractors run, in argument order:  State<AppState>, Path<Uuid>, Json<AddSampleBody>
   │  (the LAST extractor is the body-consuming one — that ordering is a type-level rule)
   ▼
the handler body (async)
   │  parse → spawn_blocking(do_* over the Plane ports) → map to a DTO
   ▼
Result<Json<Dto>, ApiError>   ──IntoResponse──▶   http::Response<Body>
   │  middleware layers run inside-out (cors_dev stamps headers on the way back)
   ▼
hyper serializes the response
```

Two ideas do all the work: **extractors** turn a raw request into typed values, and **`IntoResponse`**
turns typed values (including errors) back into a response. A handler is "just a function" precisely
because those two traits hide the HTTP plumbing.

## 2. Extractors — typed request parsing

axum calls an extractor for each handler argument:

| Extractor | What it pulls | Used by |
|---|---|---|
| `State<AppState>` | the shared app state (does NOT touch the body) | every handler |
| `Path<Uuid>` | a `{...}` path segment, parsed to `Uuid` | `/fragments/{id}`, … |
| `Query<ListFragmentsQuery>` | the `?project=…` querystring | `GET /fragments` |
| `Json<T>` | the request body, deserialized as `T` | `POST /projects`, `…/samples`, `…/references` |
| `Multipart` | a streamed `multipart/form-data` body | `POST …/fragments`, `POST /references` |

**The body-extractor-goes-last rule.** `Json` and `Multipart` consume the request body (they take it
by value), so they can appear at most once and MUST be the final argument. `State`/`Path`/`Query` only
read metadata, so they come first. This is enforced at compile time by axum's `FromRequest` vs
`FromRequestParts` split — get the order wrong and it simply won't compile.

**axum 0.8 path syntax.** Routes use braces — `"/projects/{id}/fragments"`, `"/samples/{fragmentId}"`
— NOT the `:id` colon form of axum 0.7 (the underlying `matchit` router changed in 0.8). The URLs the
client builds are unchanged (`/projects/<uuid>/fragments`); only the *registration* string differs.

## 3. Multipart — why audio is not JSON

Audio bytes never travel as JSON (that would base64-bloat them and drag a blob through the token
boundary). The client sends `multipart/form-data`; we iterate the parts:

```rust
while let Some(field) = mp.next_field().await? {
    let name = field.name().map(str::to_string); // own it: name() borrows the field…
    match name.as_deref() {                       // …and text()/bytes() consume it.
        Some("note") => note = Some(field.text().await?),
        Some("file") => bytes = Some(field.bytes().await?.to_vec()),
        ...
    }
}
```

Two gotchas baked into the code:
- **Borrow vs consume.** `field.name()` borrows the field; `field.text()/bytes()` consume it. Capture
  the name as an owned `String` first, or the borrow checker rejects the match arm.
- **Body limit.** axum's `DefaultBodyLimit` is 2 MiB — far too small for audio. We raise it to 64 MiB
  with `.layer(DefaultBodyLimit::max(MAX_UPLOAD_BYTES))`. The limit still *bounds* per-request memory,
  which is a basic DoS guard.

## 4. `State` — sharing the `Plane` across threads

axum's `State` must be `Clone + Send + Sync + 'static`. The control plane is a `Plane` holding boxed
ports. So:

```rust
#[derive(Clone)]
struct AppState { plane: Arc<Plane> }
```

`Arc<T>` is `Clone` (a refcount bump) and is `Send + Sync` **iff `T: Send + Sync`**. That forced one
upstream change: the `Plane`'s ports are now `Box<dyn Trait + Send + Sync>` (in
`nameless-cli/src/profile.rs`). Every adapter was already thread-safe — the in-memory/file fakes hold
a `Mutex` or a `PathBuf`; the Postgres/S3 adapters own a Tokio runtime + a connection pool — so adding
the bound cost nothing and is purely additive (the synchronous CLI path is unaffected). Cloning the
state per request clones the `Arc`, never the adapters.

## 5. Sync-over-async — `spawn_blocking` is not optional here

The control-plane ports are **synchronous** by design (so the lean `--local` build needs no async
runtime at all). The Postgres adapter satisfies those sync traits by owning a Tokio runtime and
`block_on`-ing internally. That detail makes the bridge load-bearing:

- Calling a sync port directly inside an `async fn` runs it **on a Tokio worker thread**. A long
  blocking call there starves the runtime; worse, the Postgres adapter's internal `block_on` **panics**
  if it runs on a thread already owned by a runtime ("Cannot start a runtime from within a runtime").
- So every handler hands the work to the blocking pool:

```rust
async fn run_blocking<T, F>(f: F) -> Result<T, ApiError>
where F: FnOnce() -> Result<T, CliError> + Send + 'static, T: Send + 'static {
    match tokio::task::spawn_blocking(f).await {
        Ok(result) => result.map_err(ApiError::from),
        Err(join) => Err(ApiError::internal(format!("task join error: {join}"))),
    }
}
```

The closure captures an `Arc<Plane>` clone (Send + 'static) plus already-parsed owned request data, so
it satisfies `spawn_blocking`'s `Send + 'static` bound. The multipart/JSON parsing happens in the async
context *before* the blocking call, so nothing is borrowed across the boundary.

## 6. Errors — one pure mapping, two body shapes

The web client (`HttpNamelessApi.parse()`) only special-cases two shapes, so the server emits exactly
those (see `error.rs`):

- **404** → `{"message": "..."}` (the client ignores the body for 404s).
- **422** → `{"error":"incomplete_attribution","missing":[…]}` for the sample gate; the `missing` array
  is the typed `AttributionField` list. Anything else → `{"message": "..."}` + a sensible status
  (`400` bad input, `503` queue backpressure, `500` otherwise).

`From<CliError> for ApiError` is the whole policy, kept pure (no I/O) so it unit-tests directly.

**The one wire subtlety worth remembering.** The `missing` field names use a *third* spelling that is
neither of the enum's built-in forms:

| field | `AttributionField::as_str()` (CLI flag) | serde `rename_all` | **wire / TS union** |
|---|---|---|---|
| source artist | `artist` | `source_artist` | **`source_artist`** |
| rights | `rights` | `rights_status` | **`rights`** |

So `attribution_field_wire()` is authored by hand to match `web/src/api/types.ts`, and a unit test
pins all seven values. (The typed `Vec<AttributionField>` reaches the HTTP layer because
`CliError::IncompleteAttribution` carries the core `IncompleteAttribution`, not a flattened string.)

## 7. The ports-over-HTTP seam (the architecture in one sentence)

HTTP is just another adapter over the control-plane core. The CLI binary and this server are two
front-ends over the **same** `do_*` use-cases and the **same** `Plane` ports; neither re-implements the
attribution gate, the content-hash/probe, or the job enqueue. The DTOs (`dto.rs`) are a pure
domain→wire projection that embeds the domain enums so their serde labels *are* the wire labels — a
label can't drift. The compact-output contract holds structurally: no DTO has a field that can carry a
waveform, a feature array, or an embedding vector (only `embedding_dim`, a count).

## 8. Testing without a network or a DB

`tower::ServiceExt::oneshot` drives the `Router` in-process: build the router over an in-memory `Plane`,
hand it one `http::Request`, await one `http::Response`. No socket, no Postgres, no worker. Because the
state is built `from_arc`, a test keeps a clone of the `Arc<Plane>` and asserts post-conditions against
the same store the handler wrote to (e.g. "a rejected sample created nothing"). That is the whole
ports-and-adapters payoff: real control flow, RAM-safe fakes.

## References

- axum 0.8 docs — extractors, `State`, `Multipart`, `middleware::from_fn`, `axum::serve`.
- tower — `ServiceExt::oneshot`, the `Service` trait the `Router` implements.
- `web/src/api/{NamelessApi,HttpNamelessApi,types,errors}.ts` — the contract this server mirrors.
- `crates/nameless-cli/src/{cli,profile,output,error}.rs` — the reused control-plane core.
