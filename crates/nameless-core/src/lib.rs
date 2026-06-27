//! # nameless-core
//!
//! The pure domain of the Nameless control plane. This crate is intentionally dependency-light
//! (serde, uuid, thiserror) and contains NO async runtime, database driver, or audio codec — so
//! it compiles in well under the 4GB budget and never drags the heavy leaf into the default build.
//!
//! It owns:
//! * the fragment data model ([`fragment`]) and provenance ([`provenance`]),
//! * the typed lifecycle state machine ([`state_machine`]) — the phase's headline invariant,
//! * the ports (trait seam) to the outside world ([`ports`]),
//! * the durable job-queue contract ([`job`]),
//! * the typed port errors ([`error`]).
//!
//! Concrete adapters (filesystem/in-memory/Postgres/S3) live in `nameless-adapters`; the CLI that
//! wires them lives in `nameless-cli`.

pub mod error;
pub mod fragment;
pub mod job;
pub mod ports;
pub mod provenance;
pub mod state_machine;

// Flat re-exports of the public surface so downstream crates can `use nameless_core::Fragment`.
pub use error::{RepoError, StoreError};
pub use fragment::{now_ms, Fragment, FragmentId, FragmentKind, Project, ProjectId};
pub use job::{JobEnvelope, JobError, JobId, JobQueue, JobRecord, JobStatus, RetryPolicy};
pub use ports::{FragmentRepo, ObjectStore};
pub use provenance::Provenance;
pub use state_machine::{transition, FragmentState, IllegalTransition, Transition};
