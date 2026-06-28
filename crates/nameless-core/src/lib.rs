//! # nameless-core
//!
//! The pure domain of the Nameless control plane. This crate is intentionally dependency-light
//! (serde, uuid, thiserror) and contains NO async runtime, database driver, or audio codec — so
//! it compiles in well under the 4GB budget and never drags the heavy leaf into the default build.
//!
//! It owns:
//! * the fragment data model ([`fragment`]) and provenance ([`provenance`]),
//! * the typed lifecycle state machine ([`state_machine`]) — the phase's headline invariant,
//! * the reference-track / non-melodic context model ([`reference`]) and the type-level
//!   melodic-vs-non-melodic conditioning barrier ([`conditioning`]) — the Phase-7 headline,
//! * the ports (trait seam) to the outside world ([`ports`]),
//! * the durable job-queue contract ([`job`]),
//! * the typed port errors ([`error`]).
//!
//! Concrete adapters (filesystem/in-memory/Postgres/S3) live in `nameless-adapters`; the CLI that
//! wires them lives in `nameless-cli`.

pub mod attribution;
pub mod conditioning;
pub mod error;
pub mod fragment;
pub mod job;
pub mod ports;
pub mod provenance;
pub mod reference;
pub mod state_machine;
pub mod stems;

// Flat re-exports of the public surface so downstream crates can `use nameless_core::Fragment`.
pub use attribution::{
    credits_sheet, AttributionField, CompleteAttribution, IncompleteAttribution, PartialAttribution,
    RightsStatus, SampleAttribution,
};
pub use conditioning::{
    gather_melodic_conditioning, MelodicConditioning, ReferenceConditioning,
};
pub use error::{RepoError, StoreError};
pub use fragment::{now_ms, Fragment, FragmentId, FragmentKind, Project, ProjectId};
pub use job::{JobEnvelope, JobError, JobId, JobQueue, JobRecord, JobStatus, RetryPolicy};
pub use ports::{
    AttributionStore, FragmentRepo, ObjectStore, ReferenceStore, SampleStore, StemStore,
};
pub use provenance::Provenance;
pub use reference::{
    ProjectReference, ReferenceContext, ReferenceContextSummary, ReferenceRole, ReferenceTrack,
    ReferenceTrackId, TonalBalance,
};
pub use state_machine::{place, transition, FragmentState, IllegalTransition, PlaceError, Transition};
pub use stems::{Stem, StemId, StemType};
