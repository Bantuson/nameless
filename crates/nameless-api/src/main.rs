//! `nameless-api` binary entrypoint.
//!
//! Builds a [`Plane`](nameless_cli::profile::Plane) via the shared `build_plane`, then serves the
//! control-plane router. Defaults to the lean `--local` profile (filesystem + in-memory adapters) so
//! it runs with no Postgres/S3; pass `--server` to select the Postgres/S3 profile, which only exists
//! when the crate is built `--features postgres` (otherwise `build_plane` returns a clear error that
//! names how to enable it).
//!
//! Env knobs:
//!   * `NAMELESS_API_ADDR` — bind address (default `127.0.0.1:8080`, matching the web client's
//!     `VITE_API_BASE_URL` default).
//!   * `NAMELESS_CORS_ALLOW_ORIGIN` — the single CORS allow-origin (default `http://localhost:5173`,
//!     the Vite dev origin). A local/dev posture, NOT a wildcard; real auth + a per-origin allowlist
//!     are a follow-up (see `nameless-api` README "Security follow-ups").
//!
//! `[env-gated]` — written to be correct; run later with `cargo run -p nameless-api`.

use std::net::SocketAddr;

use nameless_api::serve;
use nameless_cli::profile::build_plane;

// NOT #[tokio::main]: the Postgres/S3 adapters construct their OWN runtime and `block_on` a
// connect at build time (the sync-ports shim), which panics inside an already-running runtime
// ("Cannot start a runtime from within a runtime"). Build the Plane in plain sync context first,
// then start the server runtime. Per-request port calls are already safe — handlers wrap them in
// `spawn_blocking` (see handlers.rs).
fn main() {
    // Lean by default: `--local` unless `--server` is explicitly requested.
    let local = !std::env::args().any(|a| a == "--server");

    let plane = match build_plane(local) {
        Ok(plane) => plane,
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    };

    let addr: SocketAddr = std::env::var("NAMELESS_API_ADDR")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| SocketAddr::from(([127, 0, 0, 1], 8080)));

    let rt = match tokio::runtime::Builder::new_multi_thread().enable_all().build() {
        Ok(rt) => rt,
        Err(e) => {
            eprintln!("error: could not start the server runtime: {e}");
            std::process::exit(1);
        }
    };

    if let Err(e) = rt.block_on(serve(plane, addr)) {
        eprintln!("server error: {e}");
        std::process::exit(1);
    }
}
