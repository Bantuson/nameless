//! Typed errors for the core ports.
//!
//! Every port (`ObjectStore`, `FragmentRepo`, `JobQueue`) returns a typed error rather than a
//! stringly-typed or panicking failure. `thiserror` gives us `Display`/`Error` impls for free
//! while keeping the variants exhaustive and matchable by callers (the CLI maps them to exit
//! codes; future HTTP code maps them to status codes).

use thiserror::Error;

/// Failure modes of an [`crate::ports::ObjectStore`].
///
/// Deliberately backend-agnostic: the filesystem fake, the in-memory store, and the production
/// S3/R2 store all surface the same shape, so swapping the heavy leaf never changes call sites.
#[derive(Debug, Error)]
pub enum StoreError {
    /// No object exists for the requested content-hash key.
    #[error("object not found for key: {0}")]
    NotFound(String),

    /// An underlying I/O failure (filesystem or network transport).
    #[error("object store io error: {0}")]
    Io(String),

    /// The backend rejected or failed the operation for a backend-specific reason.
    #[error("object store backend error: {0}")]
    Backend(String),
}

/// Failure modes of a [`crate::ports::FragmentRepo`].
#[derive(Debug, Error)]
pub enum RepoError {
    /// The requested row does not exist.
    #[error("not found: {0}")]
    NotFound(String),

    /// An underlying I/O failure (file repo) or connection failure (Postgres repo).
    #[error("repo io error: {0}")]
    Io(String),

    /// (De)serialization of the persisted document failed.
    #[error("repo serialization error: {0}")]
    Serialization(String),

    /// The backend rejected or failed the operation (e.g. a constraint violation).
    #[error("repo backend error: {0}")]
    Backend(String),
}
