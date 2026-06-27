//! Filesystem object store — the `--local` + test fake for S3/R2.
//!
//! Objects are addressed by the SHA-256 hex of their bytes (content addressing). This gives three
//! properties for free:
//! * **immutable** — a key is a function of its bytes, so `put` never needs to overwrite;
//! * **de-duplicating** — identical audio captured twice maps to one object;
//! * **traversal-safe** — the key is hex we computed, never user input, so it cannot escape `root`.
//!
//! The production `S3ObjectStore` (behind the `postgres` feature) mirrors this exact contract over
//! an S3-compatible endpoint — same trait, swapped leaf.

use std::fs;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use nameless_core::error::StoreError;
use nameless_core::ports::ObjectStore;

/// Compute the lowercase-hex SHA-256 content hash of `bytes`. This is the object key.
///
/// Free function (not a method) because the CLI derives the key from file bytes *before* it has a
/// store instance, and the same hash is reused as the fragment's `audio_uri`.
pub fn content_hash(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    let mut out = String::with_capacity(digest.len() * 2);
    for b in digest {
        // Lowercase hex, two chars per byte.
        out.push_str(&format!("{b:02x}"));
    }
    out
}

/// An [`ObjectStore`] backed by a directory on disk.
#[derive(Debug, Clone)]
pub struct FilesystemObjectStore {
    root: PathBuf,
}

impl FilesystemObjectStore {
    /// Create a store rooted at `root` (created on first `put`).
    pub fn new(root: impl Into<PathBuf>) -> Self {
        FilesystemObjectStore { root: root.into() }
    }

    /// Map a content-hash key to its on-disk path. The key is validated to be pure lowercase hex
    /// so a malformed/hostile key can never contain a path separator or `..`.
    fn path_for(&self, key: &str) -> Result<PathBuf, StoreError> {
        if key.is_empty() || !key.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(StoreError::Backend(format!(
                "invalid object key (must be hex content hash): {key:?}"
            )));
        }
        Ok(self.root.join(key))
    }
}

impl ObjectStore for FilesystemObjectStore {
    fn put(&self, key: &str, bytes: &[u8]) -> Result<(), StoreError> {
        let path = self.path_for(key)?;
        // Write-if-absent: under content addressing the bytes are identical, so an existing key is
        // a no-op success (immutability — we never rewrite/mutate an existing object).
        if path.exists() {
            return Ok(());
        }
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| StoreError::Io(e.to_string()))?;
        }
        // Write to a temp sibling then rename, so a crash mid-write never leaves a half object
        // under a content-hash key (which would otherwise read as valid).
        let tmp = path.with_extension("tmp");
        fs::write(&tmp, bytes).map_err(|e| StoreError::Io(e.to_string()))?;
        fs::rename(&tmp, &path).map_err(|e| StoreError::Io(e.to_string()))?;
        Ok(())
    }

    fn get(&self, key: &str) -> Result<Vec<u8>, StoreError> {
        let path = self.path_for(key)?;
        match fs::read(&path) {
            Ok(bytes) => Ok(bytes),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                Err(StoreError::NotFound(key.to_string()))
            }
            Err(e) => Err(StoreError::Io(e.to_string())),
        }
    }

    fn exists(&self, key: &str) -> Result<bool, StoreError> {
        let path = self.path_for(key)?;
        Ok(Path::new(&path).exists())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    /// A throwaway unique tempdir under the OS temp dir (no external tempfile dep).
    fn tempdir(tag: &str) -> PathBuf {
        let mut p = env::temp_dir();
        let uniq = format!(
            "nameless-fs-test-{tag}-{}",
            content_hash(format!("{:?}{tag}", std::time::SystemTime::now()).as_bytes())
        );
        p.push(uniq);
        p
    }

    #[test]
    fn content_hash_is_deterministic_and_distinct() {
        assert_eq!(content_hash(b"abc"), content_hash(b"abc"));
        assert_ne!(content_hash(b"abc"), content_hash(b"abd"));
        // Known SHA-256 of "abc".
        assert_eq!(
            content_hash(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn put_is_immutable_and_get_round_trips() {
        let dir = tempdir("immut");
        let store = FilesystemObjectStore::new(&dir);
        let bytes = b"the quick brown fox";
        let key = content_hash(bytes);

        assert!(!store.exists(&key).unwrap());
        store.put(&key, bytes).unwrap();
        assert!(store.exists(&key).unwrap());
        assert_eq!(store.get(&key).unwrap(), bytes);

        // Second put of the same key is a no-op success; bytes unchanged.
        store.put(&key, bytes).unwrap();
        assert_eq!(store.get(&key).unwrap(), bytes);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn get_missing_is_not_found() {
        let dir = tempdir("missing");
        let store = FilesystemObjectStore::new(&dir);
        let key = content_hash(b"never stored");
        match store.get(&key) {
            Err(StoreError::NotFound(_)) => {}
            other => panic!("expected NotFound, got {other:?}"),
        }
    }

    #[test]
    fn rejects_non_hex_key() {
        let store = FilesystemObjectStore::new(tempdir("badkey"));
        assert!(store.get("../etc/passwd").is_err());
        assert!(store.put("../escape", b"x").is_err());
    }
}
