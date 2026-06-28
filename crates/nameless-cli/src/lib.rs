//! # nameless-cli (library surface)
//!
//! Historically this crate was a binary only: `main.rs` declared the modules privately and nothing
//! could reuse them. Phase 10 adds the control-plane **HTTP API** (`nameless-api`), which must run
//! the EXACT same control-plane use-cases the `nameless` CLI exposes — `build_plane`, the assembled
//! [`profile::Plane`], and the `do_*` functions (`do_capture`/`do_reference_upload`/
//! `do_stems_separate`/`do_sample_add`/`do_create_project`, plus the byte-based
//! `do_capture_bytes`/`do_reference_upload_bytes` the HTTP multipart path needs) — rather than
//! re-implement the integrity logic (the attribution gate, content-hashing, probing, enqueueing).
//!
//! So the modules are now exposed as a library. The `nameless` binary (`main.rs`) depends on this
//! same library, so there is one source of truth for the command logic and the HTTP veneer is exactly
//! that: a thin transport over these functions. This is the ports-and-adapters law applied across the
//! process boundary — HTTP is just another adapter over the control-plane core.
//!
//! Nothing here is async or HTTP-aware; the `Plane` ports are synchronous (see
//! `nameless-core/src/ports.rs`). The HTTP server bridges sync↔async with `spawn_blocking` at its own
//! boundary (documented in `nameless-api`).

pub mod cli;
pub mod error;
pub mod output;
pub mod profile;
