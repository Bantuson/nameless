//! # nameless-adapters
//!
//! Concrete adapters behind the `nameless-core` ports. The split is the whole point:
//!
//! * **Default features (pure Rust, 4GB-buildable):** [`FilesystemObjectStore`],
//!   [`InMemoryObjectStore`], [`InMemoryFragmentRepo`], [`FileFragmentRepo`], the symphonia
//!   [`probe`], and [`InMemoryJobQueue`].
//! * **`postgres` feature (heavy leaf, env-gated):** `PostgresFragmentRepo`, `SqlxmqJobQueue`,
//!   `S3ObjectStore` — tokio + sqlx + sqlxmq + an S3 client. Not pulled into the default build.
//!
//! Every adapter implements a trait from `nameless-core`, so the production and local
//! implementations are interchangeable at the call site.

pub mod object_store_fs;
pub mod object_store_mem;
pub mod probe;
pub mod queue_mem;
pub mod reference_store_file;
pub mod reference_store_mem;
pub mod repo_file;
pub mod repo_mem;

// --- heavy leaf, behind the non-default `postgres` feature ---
#[cfg(feature = "postgres")]
pub mod object_store_s3;
#[cfg(feature = "postgres")]
pub mod queue_sqlxmq;
#[cfg(feature = "postgres")]
pub mod reference_store_pg;
#[cfg(feature = "postgres")]
pub mod repo_pg;

// Re-export the default (lean) adapter surface.
pub use object_store_fs::{content_hash, FilesystemObjectStore};
pub use object_store_mem::InMemoryObjectStore;
pub use probe::{probe, ProbeResult};
pub use queue_mem::InMemoryJobQueue;
pub use reference_store_file::FileReferenceStore;
pub use reference_store_mem::InMemoryReferenceStore;
pub use repo_file::FileFragmentRepo;
pub use repo_mem::InMemoryFragmentRepo;

#[cfg(feature = "postgres")]
pub use object_store_s3::S3ObjectStore;
#[cfg(feature = "postgres")]
pub use queue_sqlxmq::SqlxmqJobQueue;
#[cfg(feature = "postgres")]
pub use reference_store_pg::PostgresReferenceStore;
#[cfg(feature = "postgres")]
pub use repo_pg::PostgresFragmentRepo;
