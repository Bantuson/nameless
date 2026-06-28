//! Ports — the trait seam between the domain and the outside world.
//!
//! These traits are the single architectural decision that makes RAM-safe verification honest:
//! the production heavy leaf (S3/R2, Postgres) and the local fake (filesystem, in-memory)
//! implement the SAME trait, so local tests exercise real control flow with only the heavy leaf
//! swapped. Core logic depends on these traits, never on a concrete adapter.
//!
//! ## Why the traits are synchronous
//!
//! The `--local` capture loop is fully synchronous and must compile with NO async runtime in the
//! dependency tree (the default build stays lean for the 4GB box). The production Postgres/S3
//! adapters are async *internally*, but they satisfy these sync traits by owning a Tokio runtime
//! and `block_on`-ing at the boundary — the async-ness never leaks into the core or the default
//! build. This keeps one port shape for both worlds at the cost of a thin blocking shim in the
//! heavy adapters (documented there).

use crate::attribution::SampleAttribution;
use crate::error::{RepoError, StoreError};
use crate::fragment::{Fragment, FragmentId, Project, ProjectId};
use crate::reference::{
    ProjectReference, ReferenceContextSummary, ReferenceRole, ReferenceTrack, ReferenceTrackId,
};
use crate::stems::{Stem, StemId};

/// Immutable, content-addressed blob storage (raw audio, later rendered audio + stems).
///
/// Objects are keyed by the SHA-256 hex of their bytes, so the store is de-duplicating and
/// immutable by construction: the same bytes always map to the same key, and `put` never mutates
/// an existing key. Implementors: `FilesystemObjectStore` (local/test), `InMemoryObjectStore`
/// (test), `S3ObjectStore` (prod, behind the `postgres` feature).
pub trait ObjectStore {
    /// Store `bytes` under `key`. MUST be write-if-absent: if `key` already exists, leave the
    /// stored bytes unchanged (they are identical anyway under content addressing) and succeed.
    fn put(&self, key: &str, bytes: &[u8]) -> Result<(), StoreError>;

    /// Fetch the bytes for `key`, or `StoreError::NotFound` if absent.
    fn get(&self, key: &str) -> Result<Vec<u8>, StoreError>;

    /// Whether `key` exists.
    fn exists(&self, key: &str) -> Result<bool, StoreError>;
}

/// Persistence for the fragment graph (projects + fragments).
///
/// Implementors: `InMemoryFragmentRepo` (state-machine/unit tests), `FileFragmentRepo`
/// (the `--local` JSON-file store, survives across process invocations), `PostgresFragmentRepo`
/// (prod, behind the `postgres` feature).
pub trait FragmentRepo {
    /// Insert a project.
    fn insert_project(&self, p: &Project) -> Result<(), RepoError>;

    /// Insert a fragment.
    fn insert_fragment(&self, f: &Fragment) -> Result<(), RepoError>;

    /// List fragments, optionally filtered to a single project. Newest-first is encouraged but
    /// not required by the contract; callers that need ordering should sort explicitly.
    fn list_fragments(&self, project: Option<ProjectId>) -> Result<Vec<Fragment>, RepoError>;

    /// Fetch a single fragment by id, or `Ok(None)` if it does not exist.
    fn get_fragment(&self, id: FragmentId) -> Result<Option<Fragment>, RepoError>;
}

/// Persistence for reference tracks + their attachments to projects (Phase 7).
///
/// Mirrors the [`FragmentRepo`] split of responsibilities: the Rust control plane owns the
/// `reference_tracks` rows (on upload) and the `project_reference_context` link (on attach). The
/// `reference_context` row — the embedding + non-melodic targets + vibe — is WRITTEN BY THE PYTHON
/// ANALYZER (exactly as `fragment_features` is, not by Rust), and the control plane only READS it
/// back as a compact [`ReferenceContextSummary`] for `reference show`. That summary deliberately
/// carries no embedding vector and no melodic field (the compact-output + non-cloning contracts).
///
/// Implementors: `InMemoryReferenceStore` (tests), `FileReferenceStore` (the `--local` JSON store),
/// `PostgresReferenceStore` (prod, behind the `postgres` feature).
pub trait ReferenceStore {
    /// Insert an uploaded reference track.
    fn insert_track(&self, track: &ReferenceTrack) -> Result<(), RepoError>;

    /// Fetch a single reference track by id, or `Ok(None)` if absent.
    fn get_track(&self, id: ReferenceTrackId) -> Result<Option<ReferenceTrack>, RepoError>;

    /// List all reference tracks (newest-first encouraged; callers needing order should sort).
    fn list_tracks(&self) -> Result<Vec<ReferenceTrack>, RepoError>;

    /// Read the COMPACT, array-free context summary for a reference (for `reference show`).
    /// `Ok(None)` when the track exists but has not been analyzed yet (the Python worker is the
    /// writer). The full embedding vector is never returned through this port.
    fn get_context_summary(
        &self,
        id: ReferenceTrackId,
    ) -> Result<Option<ReferenceContextSummary>, RepoError>;

    /// Attach a reference to a project with a role (idempotent upsert on the composite key).
    fn attach(
        &self,
        project: ProjectId,
        reference: ReferenceTrackId,
        role: ReferenceRole,
    ) -> Result<(), RepoError>;

    /// List the references attached to a project, with their roles.
    fn list_project_references(
        &self,
        project: ProjectId,
    ) -> Result<Vec<ProjectReference>, RepoError>;
}

/// Persistence for the retained stem library (Phase 8 — SAMP-01).
///
/// The Python `DemucsStemSeparator` WRITES these rows (mirroring how the feature worker writes
/// `fragment_features`); the control plane READS them for `stems list` and resolves a stem to its
/// `audio_uri` when promoting it to a `sampled` fragment. The stem audio itself lives in the
/// [`ObjectStore`] by content-hash, retained indefinitely — only the index lives here.
///
/// Implementors: `InMemorySampleStore` (tests), `FileSampleStore` (the `--local` JSON store),
/// `PostgresSampleStore` (prod, behind the `postgres` feature).
pub trait StemStore {
    /// Insert a stem index row (idempotent on `id`; the audio is already in the object store).
    fn insert_stem(&self, stem: &Stem) -> Result<(), RepoError>;

    /// Fetch a single stem by id, or `Ok(None)` if absent.
    fn get_stem(&self, id: StemId) -> Result<Option<Stem>, RepoError>;

    /// List the stems separated from one uploaded track (browsable; newest-first encouraged).
    fn list_stems(&self, track: ReferenceTrackId) -> Result<Vec<Stem>, RepoError>;
}

/// Persistence for sample attributions (Phase 8 — SAMP-03/SAMP-05).
///
/// A row exists iff a fragment has `provenance = sampled`. Because a [`SampleAttribution`] is built
/// only from a [`crate::attribution::CompleteAttribution`], every persisted attribution is complete
/// by construction — the credits exporter ([`crate::attribution::credits_sheet`]) just reads them.
pub trait AttributionStore {
    /// Insert a (complete) sample attribution for a sampled fragment.
    fn insert_attribution(&self, attribution: &SampleAttribution) -> Result<(), RepoError>;

    /// Fetch the attribution for a sampled fragment, or `Ok(None)` if it has none.
    fn get_attribution(&self, fragment: FragmentId) -> Result<Option<SampleAttribution>, RepoError>;

    /// List every sample attribution in a project (drives `credits <project>`).
    fn list_project_attributions(
        &self,
        project: ProjectId,
    ) -> Result<Vec<SampleAttribution>, RepoError>;
}

/// A combined stem + attribution store — one object that satisfies both Phase-8 ports.
///
/// The local/file and Postgres adapters back stems and attributions with the same store (one JSON
/// file / one database), so this supertrait lets the CLI hold a single `Box<dyn SampleStore>` and
/// call either port's methods through it. The blanket impl means any type implementing both halves
/// is automatically a `SampleStore` — no per-adapter boilerplate.
pub trait SampleStore: StemStore + AttributionStore {}

impl<T: StemStore + AttributionStore> SampleStore for T {}
