//! Profiles — wire the core ports to concrete adapters from CLI flags / environment.
//!
//! A [`Plane`] is the assembled set of adapters the command handlers run against, held as boxed
//! trait objects so the SAME handler code runs over the local fakes or the production backends.
//!
//! * `--local` → [`FilesystemObjectStore`] + [`FileFragmentRepo`] + [`InMemoryJobQueue`], all under
//!   `.nameless-local/`. No Postgres, no network — this is what makes the walking skeleton run on
//!   the 4GB box.
//! * server (no `--local`) → Postgres + sqlxmq + S3/R2, built from env vars. ONLY available when
//!   compiled `--features postgres`; otherwise the binary stays lean and tells the user to use
//!   `--local`.

use std::path::PathBuf;

use nameless_core::ports::{FragmentRepo, JobQueue, ObjectStore, ReferenceStore};

use nameless_adapters::{
    FileFragmentRepo, FileReferenceStore, FilesystemObjectStore, InMemoryJobQueue,
};

use crate::error::CliError;

/// The assembled control-plane adapters a command runs against.
pub struct Plane {
    pub store: Box<dyn ObjectStore>,
    pub repo: Box<dyn FragmentRepo>,
    pub queue: Box<dyn JobQueue>,
    /// Reference-track persistence (Phase 7) — uploads, context summaries, project links.
    pub references: Box<dyn ReferenceStore>,
}

/// Default bounded capacity for the `--local` in-memory queue.
const LOCAL_QUEUE_CAPACITY: usize = 1024;

/// Root directory for the `--local` profile's on-disk state.
const LOCAL_ROOT: &str = ".nameless-local";

/// Build a [`Plane`] from the parsed flags.
///
/// `local = true` selects the filesystem/file/in-memory profile. `local = false` selects the
/// server profile, which only exists under the `postgres` feature.
pub fn build_plane(local: bool) -> Result<Plane, CliError> {
    if local {
        return Ok(local_plane());
    }
    server_plane()
}

/// The `--local` profile: filesystem object store + JSON file repo + in-memory queue.
fn local_plane() -> Plane {
    let root = PathBuf::from(LOCAL_ROOT);
    let store = FilesystemObjectStore::new(root.join("objects"));
    let repo = FileFragmentRepo::new(root.join("db.json"));
    // NOTE: the --local queue is process-local (in-memory). The enqueue on capture is real and
    // tested, but durable cross-restart delivery is the sqlxmq path (server profile). Do not
    // mistake this for durable local delivery.
    let queue = InMemoryJobQueue::new(LOCAL_QUEUE_CAPACITY);
    // File-backed reference store so `reference upload` then `reference show` survive across
    // separate `--local` process invocations (same JSON-file durability as the fragment repo).
    let references = FileReferenceStore::new(root.join("references.json"));
    Plane {
        store: Box::new(store),
        repo: Box::new(repo),
        queue: Box::new(queue),
        references: Box::new(references),
    }
}

/// The server profile (Postgres + sqlxmq + S3/R2), behind the `postgres` feature.
#[cfg(feature = "postgres")]
fn server_plane() -> Result<Plane, CliError> {
    use nameless_adapters::{
        PostgresFragmentRepo, PostgresReferenceStore, S3ObjectStore, SqlxmqJobQueue,
    };

    let database_url = std::env::var("DATABASE_URL")
        .map_err(|_| CliError::Config("DATABASE_URL is required for the server profile".into()))?;

    let repo = PostgresFragmentRepo::connect(&database_url)
        .map_err(|e| CliError::Config(format!("connect Postgres repo: {e}")))?;
    let queue = SqlxmqJobQueue::connect(&database_url)
        .map_err(|e| CliError::Config(format!("connect sqlxmq queue: {e}")))?;
    let store = S3ObjectStore::from_env()
        .map_err(|e| CliError::Config(format!("connect S3/R2 store: {e}")))?;
    let references = PostgresReferenceStore::connect(&database_url)
        .map_err(|e| CliError::Config(format!("connect Postgres reference store: {e}")))?;

    Ok(Plane {
        store: Box::new(store),
        repo: Box::new(repo),
        queue: Box::new(queue),
        references: Box::new(references),
    })
}

/// Without the `postgres` feature the server profile does not exist — guide the user to `--local`.
#[cfg(not(feature = "postgres"))]
fn server_plane() -> Result<Plane, CliError> {
    Err(CliError::Config(
        "this build has no server profile; pass --local, or rebuild with --features postgres for \
         the Postgres/S3 backend"
            .into(),
    ))
}
