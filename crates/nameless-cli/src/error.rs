//! CLI-level error type. Maps the typed port errors + I/O + config problems to a single error the
//! `main` entrypoint renders as a one-line message + non-zero exit code.

use thiserror::Error;

use nameless_core::error::{RepoError, StoreError};
use nameless_core::job::JobError;

#[derive(Debug, Error)]
pub enum CliError {
    #[error("io error reading {path}: {source}")]
    ReadFile {
        path: String,
        #[source]
        source: std::io::Error,
    },

    #[error("object store error: {0}")]
    Store(#[from] StoreError),

    #[error("repo error: {0}")]
    Repo(#[from] RepoError),

    #[error("job queue error: {0}")]
    Job(#[from] JobError),

    #[error("not found: {0}")]
    NotFound(String),

    /// A `sample add` was rejected because attribution was incomplete (SAMP-03). The message names
    /// exactly which fields are missing; nothing was created.
    #[error("{0}")]
    IncompleteAttribution(String),

    #[error("configuration error: {0}")]
    Config(String),
}
