//! CLI-level error type. Maps the typed port errors + I/O + config problems to a single error the
//! `main` entrypoint renders as a one-line message + non-zero exit code.

use thiserror::Error;

use nameless_core::attribution::IncompleteAttribution;
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

    /// A `sample add` was rejected because attribution was incomplete (SAMP-03). Carries the TYPED
    /// list of missing fields (not just a message) so every consumer can render them structurally:
    /// the CLI prints the joined `Display`, and the Phase-10 HTTP API serializes the field names into
    /// the `422 {"error":"incomplete_attribution","missing":[…]}` body the web client parses. Nothing
    /// was created when this is returned (the gate runs before any write).
    #[error("{0}")]
    IncompleteAttribution(#[from] IncompleteAttribution),

    /// A `sample add` was rejected because the requested slice lies outside the stem's known length
    /// (SAMP-05 — the credits sheet must not record a range the source does not contain). Nothing
    /// was created.
    #[error("{0}")]
    SampleOutOfRange(String),

    #[error("configuration error: {0}")]
    Config(String),
}
