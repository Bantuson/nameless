//! Shared application state — the assembled control-plane [`Plane`], behind an `Arc`.
//!
//! axum's `State` must be `Clone + Send + Sync + 'static`. The [`Plane`] holds the control-plane
//! ports as `Box<dyn Trait + Send + Sync>` (see `nameless-cli/src/profile.rs`), so the `Plane` is
//! `Send + Sync` and an `Arc<Plane>` is cheap to clone per request and shareable across the Tokio
//! worker threads. Cloning `AppState` clones the `Arc` (a refcount bump), never the adapters.
//!
//! The handlers never mutate this state directly; all writes go through the `Plane`'s ports (which
//! are internally synchronised — `Mutex` in the local fakes, a connection pool in Postgres).

use std::sync::Arc;

use nameless_cli::profile::Plane;

/// The axum shared state: one `Arc`-shared [`Plane`] for the whole server.
#[derive(Clone)]
pub struct AppState {
    pub plane: Arc<Plane>,
}

impl AppState {
    /// Wrap an owned [`Plane`] (the normal server path: `build_plane(local)` → `AppState::new`).
    pub fn new(plane: Plane) -> Self {
        Self {
            plane: Arc::new(plane),
        }
    }

    /// Build from an already-shared [`Plane`]. Used by the integration tests so the test can KEEP a
    /// clone of the `Arc` to assert post-conditions against the same store the router writes to
    /// (e.g. "a rejected sample created nothing").
    pub fn from_arc(plane: Arc<Plane>) -> Self {
        Self { plane }
    }
}
