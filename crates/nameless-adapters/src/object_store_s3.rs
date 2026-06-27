//! Production object store on S3-compatible storage (Cloudflare R2) — behind the `postgres`
//! feature. Mirrors the [`FilesystemObjectStore`](crate::object_store_fs::FilesystemObjectStore)
//! contract: immutable, content-addressed (SHA-256 hex key), de-duplicating.
//!
//! ## Client choice: `rust-s3`
//!
//! We use the lighter `rust-s3` crate rather than `aws-sdk-s3`. Rationale: this is a local-first,
//! solo build talking to R2 via a custom endpoint; `rust-s3` covers put/get/head cleanly with a
//! far smaller dependency tree, which matters for compile time/RAM on the env-gated heavy build.
//! The trait boundary means swapping to `aws-sdk-s3` later is a one-file change.
//!
//! ## Immutability on object storage
//!
//! Under content addressing the key IS the hash of the bytes, so re-putting a key always writes
//! identical bytes — there is nothing to corrupt. We still `head` first and skip the upload when
//! the object exists, to avoid needless writes and to match the filesystem fake's write-if-absent
//! semantics. (R2 also supports `If-None-Match: *` conditional PUT; the head-then-put path is used
//! here for portability across S3-compatible backends.)

use std::sync::Arc;

use s3::bucket::Bucket;
use s3::creds::Credentials;
use s3::region::Region;
use tokio::runtime::Runtime;

use nameless_core::error::StoreError;
use nameless_core::ports::ObjectStore;

/// Configuration sourced from `NAMELESS_STORAGE_*` env vars.
#[derive(Debug, Clone)]
pub struct S3Config {
    pub bucket: String,
    pub endpoint: String,
    pub region: String,
    pub access_key_id: String,
    pub secret_access_key: String,
}

impl S3Config {
    /// Read config from the environment (`NAMELESS_STORAGE_*`).
    pub fn from_env() -> Result<Self, StoreError> {
        let get = |k: &str| {
            std::env::var(k).map_err(|_| StoreError::Backend(format!("missing env var {k}")))
        };
        Ok(S3Config {
            bucket: get("NAMELESS_STORAGE_BUCKET")?,
            endpoint: get("NAMELESS_STORAGE_ENDPOINT")?,
            region: std::env::var("NAMELESS_STORAGE_REGION").unwrap_or_else(|_| "auto".into()),
            access_key_id: get("NAMELESS_STORAGE_ACCESS_KEY_ID")?,
            secret_access_key: get("NAMELESS_STORAGE_SECRET_ACCESS_KEY")?,
        })
    }
}

/// An [`ObjectStore`] backed by an S3-compatible bucket (R2).
pub struct S3ObjectStore {
    rt: Arc<Runtime>,
    bucket: Box<Bucket>,
}

impl S3ObjectStore {
    /// Build from `NAMELESS_STORAGE_*` env vars with a fresh owned runtime.
    pub fn from_env() -> Result<Self, StoreError> {
        let cfg = S3Config::from_env()?;
        let rt = Arc::new(Runtime::new().map_err(|e| StoreError::Io(e.to_string()))?);
        Self::new(rt, &cfg)
    }

    /// Build from explicit config + a (possibly shared) runtime.
    pub fn new(rt: Arc<Runtime>, cfg: &S3Config) -> Result<Self, StoreError> {
        let region = Region::Custom {
            region: cfg.region.clone(),
            endpoint: cfg.endpoint.clone(),
        };
        let creds = Credentials::new(
            Some(&cfg.access_key_id),
            Some(&cfg.secret_access_key),
            None,
            None,
            None,
        )
        .map_err(|e| StoreError::Backend(e.to_string()))?;

        // Path-style addressing is the portable choice for custom S3-compatible endpoints.
        let bucket = Bucket::new(&cfg.bucket, region, creds)
            .map_err(|e| StoreError::Backend(e.to_string()))?
            .with_path_style();

        Ok(Self { rt, bucket })
    }

    /// Validate the content-hash key shape (defence in depth — keys are always our hex hashes).
    fn check_key(key: &str) -> Result<(), StoreError> {
        if key.is_empty() || !key.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(StoreError::Backend(format!(
                "invalid object key (must be hex content hash): {key:?}"
            )));
        }
        Ok(())
    }
}

impl ObjectStore for S3ObjectStore {
    fn put(&self, key: &str, bytes: &[u8]) -> Result<(), StoreError> {
        Self::check_key(key)?;
        // Write-if-absent: skip the upload when the immutable object already exists.
        if self.exists(key)? {
            return Ok(());
        }
        self.rt.block_on(async {
            let resp = self
                .bucket
                .put_object(format!("/{key}"), bytes)
                .await
                .map_err(|e| StoreError::Backend(e.to_string()))?;
            let code = resp.status_code();
            if (200..300).contains(&code) {
                Ok(())
            } else {
                Err(StoreError::Backend(format!("put returned HTTP {code}")))
            }
        })
    }

    fn get(&self, key: &str) -> Result<Vec<u8>, StoreError> {
        Self::check_key(key)?;
        self.rt.block_on(async {
            let resp = self
                .bucket
                .get_object(format!("/{key}"))
                .await
                .map_err(|e| StoreError::Backend(e.to_string()))?;
            match resp.status_code() {
                200 => Ok(resp.bytes().to_vec()),
                404 => Err(StoreError::NotFound(key.to_string())),
                code => Err(StoreError::Backend(format!("get returned HTTP {code}"))),
            }
        })
    }

    fn exists(&self, key: &str) -> Result<bool, StoreError> {
        Self::check_key(key)?;
        self.rt.block_on(async {
            match self.bucket.head_object(format!("/{key}")).await {
                Ok((_head, code)) if code == 200 => Ok(true),
                Ok((_head, 404)) => Ok(false),
                Ok((_head, code)) => Err(StoreError::Backend(format!("head returned HTTP {code}"))),
                // Treat a 404-shaped transport error as "absent"; surface anything else.
                Err(e) => {
                    let msg = e.to_string();
                    if msg.contains("404") {
                        Ok(false)
                    } else {
                        Err(StoreError::Backend(msg))
                    }
                }
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object_store_fs::content_hash;

    // Live-bucket round-trip + immutability. Ignored by default; run with:
    //   NAMELESS_STORAGE_*=... cargo test -p nameless-adapters --features postgres -- --ignored s3
    #[test]
    #[ignore = "requires a live S3/R2 bucket (NAMELESS_STORAGE_*)"]
    fn put_get_by_content_hash_round_trips_and_is_immutable() {
        let store = S3ObjectStore::from_env().unwrap();
        let bytes = b"nameless s3 round-trip bytes";
        let key = content_hash(bytes);

        store.put(&key, bytes).unwrap();
        assert!(store.exists(&key).unwrap());
        assert_eq!(store.get(&key).unwrap(), bytes);

        // Re-put of the same key is a no-op and does not mutate the stored bytes.
        store.put(&key, bytes).unwrap();
        assert_eq!(store.get(&key).unwrap(), bytes);
    }
}
