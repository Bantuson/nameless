//! # nameless-api
//!
//! The control-plane **HTTP API** — an axum 0.8 server that exposes the EXACT contract the Phase-9
//! web UI (`web/src/api/HttpNamelessApi.ts`) was written against, as a thin veneer over the
//! `nameless-cli` control-plane use-cases. No new domain logic, no weakened integrity boundary: the
//! attribution gate, content-hashing, probing, and job enqueue all stay in the reused `do_*`
//! functions ([`nameless_cli::cli`]).
//!
//! ## The seam
//!
//! ```text
//!   HTTP request ──▶ axum handler ──▶ spawn_blocking ──▶ do_* over the Plane ports ──▶ DTO ──▶ JSON
//! ```
//!
//! * **State** is `AppState { plane: Arc<Plane> }`. The `Plane`'s ports are `dyn … + Send + Sync`, so
//!   the `Arc` is `Clone + Send + Sync` — axum's `State` requirement (see [`state`]).
//! * **Sync over async:** the ports are synchronous (and the Postgres adapter `block_on`s inside), so
//!   each handler runs the use-case in [`tokio::task::spawn_blocking`] rather than calling it on a
//!   Tokio worker thread (see [`handlers`]).
//! * **Errors** map purely from `CliError` to status + body (see [`error`]); the web client parses
//!   `404` and `422 {"error":"incomplete_attribution","missing":[…]}` specially.
//!
//! ## Build profiles
//!
//! The default build serves the lean `--local` profile (filesystem + in-memory adapters); the
//! Postgres/S3 server `Plane` is behind `--features postgres` (propagated to `nameless-cli`). The
//! whole crate is `[env-gated]` — it is written to be correct by review and exercised by
//! `cargo test -p nameless-api`, but NOT compiled or run on the 4GB course box.

pub mod dto;
pub mod error;
pub mod handlers;
pub mod state;

use std::net::SocketAddr;

use axum::body::Body;
use axum::extract::DefaultBodyLimit;
use axum::extract::Request;
use axum::http::{header, HeaderValue, Method};
use axum::middleware::{self, Next};
use axum::response::Response;
use axum::routing::{get, post};
use axum::Router;

use nameless_cli::profile::Plane;

pub use state::AppState;

/// Upload ceiling for the multipart routes (capture + reference upload). axum's default body limit
/// is 2 MiB — far too small for an audio file — so we raise it. 64 MiB comfortably covers a few
/// minutes of WAV while still bounding memory per request (a basic DoS guard).
pub const MAX_UPLOAD_BYTES: usize = 64 * 1024 * 1024;

/// Build the full control-plane router over an [`AppState`].
///
/// Routes use axum 0.8 path syntax — `{id}`, NOT the `:id` of axum 0.7 — but resolve to the SAME
/// URLs the client builds (`/projects/<uuid>/fragments`, …). Every path/method here mirrors
/// `HttpNamelessApi.ts` exactly.
pub fn build_router(state: AppState) -> Router {
    Router::new()
        // ---- projects ----
        .route(
            "/projects",
            get(handlers::list_projects).post(handlers::create_project),
        )
        // ---- capture (UI-01) ----
        .route("/projects/{id}/fragments", post(handlers::capture))
        .route("/fragments", get(handlers::list_fragments))
        .route("/fragments/{id}", get(handlers::get_fragment))
        // ---- reference (UI-02) ----
        .route(
            "/references",
            get(handlers::list_references).post(handlers::upload_reference),
        )
        .route("/references/{id}", get(handlers::get_reference))
        .route("/projects/{id}/references", post(handlers::attach_reference))
        // ---- stem library + sampling (UI-03) ----
        .route("/tracks/{id}/stems/separate", post(handlers::separate_stems))
        .route("/tracks/{id}/stems", get(handlers::list_stems))
        .route("/projects/{id}/samples", post(handlers::add_sample))
        .route("/samples/{fragmentId}", get(handlers::get_sample))
        // ---- project graph + credits (UI-04) ----
        .route("/projects/{id}/graph", get(handlers::project_graph))
        .route("/projects/{id}/credits", get(handlers::get_credits))
        // Raise the body limit so audio uploads fit (applies to the multipart routes).
        .layer(DefaultBodyLimit::max(MAX_UPLOAD_BYTES))
        // Permissive dev CORS so the Vite dev server (a different origin) can call the API. This is a
        // DEV default only — see the README "Security follow-ups"; a real deployment must pin origins.
        .layer(middleware::from_fn(cors_dev))
        .with_state(state)
}

/// A minimal, dependency-free permissive CORS layer for local development.
///
/// It answers `OPTIONS` preflights with an empty 200 and stamps `Access-Control-Allow-*: *`-style
/// headers on every response. Intentionally permissive and intentionally NOT production-grade
/// (no credentialed-origin handling, no per-origin allowlist) — that hardening is a documented
/// follow-up, out of scope for this phase.
async fn cors_dev(req: Request, next: Next) -> Response {
    let is_preflight = req.method() == Method::OPTIONS;
    let mut res = if is_preflight {
        Response::new(Body::empty())
    } else {
        next.run(req).await
    };
    let headers = res.headers_mut();
    headers.insert(
        header::ACCESS_CONTROL_ALLOW_ORIGIN,
        HeaderValue::from_static("*"),
    );
    headers.insert(
        header::ACCESS_CONTROL_ALLOW_METHODS,
        HeaderValue::from_static("GET, POST, OPTIONS"),
    );
    headers.insert(
        header::ACCESS_CONTROL_ALLOW_HEADERS,
        HeaderValue::from_static("content-type, accept"),
    );
    res
}

/// Bind `addr` and serve the control plane over the given [`Plane`]. Consumes the `Plane` (moves it
/// into the shared [`AppState`]). Returns when the server stops (or fails to bind).
pub async fn serve(plane: Plane, addr: SocketAddr) -> std::io::Result<()> {
    let app = build_router(AppState::new(plane));
    let listener = tokio::net::TcpListener::bind(addr).await?;
    eprintln!("nameless-api listening on http://{addr}");
    axum::serve(listener, app).await
}
