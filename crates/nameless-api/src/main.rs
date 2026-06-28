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
//!
//! `[env-gated]` — written to be correct; run later with `cargo run -p nameless-api`.

use std::net::SocketAddr;

use nameless_api::serve;
use nameless_cli::profile::build_plane;

#[tokio::main]
async fn main() {
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

    if let Err(e) = serve(plane, addr).await {
        eprintln!("server error: {e}");
        std::process::exit(1);
    }
}
