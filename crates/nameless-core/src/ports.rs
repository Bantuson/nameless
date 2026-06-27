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

use crate::error::{RepoError, StoreError};
use crate::fragment::{Fragment, FragmentId, Project, ProjectId};

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
