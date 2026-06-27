//! In-memory object store — a pure-RAM [`ObjectStore`] for unit tests.
//!
//! Same content-addressed contract as the filesystem/S3 stores, with no disk I/O, so tests of
//! capture/storage flow run fast and leave nothing behind.

use std::collections::HashMap;
use std::sync::Mutex;

use nameless_core::error::StoreError;
use nameless_core::ports::ObjectStore;

/// An [`ObjectStore`] backed by an in-memory map. Immutable: `put` of an existing key is a no-op.
#[derive(Debug, Default)]
pub struct InMemoryObjectStore {
    objects: Mutex<HashMap<String, Vec<u8>>>,
}

impl InMemoryObjectStore {
    pub fn new() -> Self {
        Self::default()
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, HashMap<String, Vec<u8>>>, StoreError> {
        self.objects
            .lock()
            .map_err(|_| StoreError::Backend("object store mutex poisoned".into()))
    }
}

impl ObjectStore for InMemoryObjectStore {
    fn put(&self, key: &str, bytes: &[u8]) -> Result<(), StoreError> {
        let mut map = self.lock()?;
        // Write-if-absent (immutable under content addressing).
        map.entry(key.to_string()).or_insert_with(|| bytes.to_vec());
        Ok(())
    }

    fn get(&self, key: &str) -> Result<Vec<u8>, StoreError> {
        let map = self.lock()?;
        map.get(key)
            .cloned()
            .ok_or_else(|| StoreError::NotFound(key.to_string()))
    }

    fn exists(&self, key: &str) -> Result<bool, StoreError> {
        let map = self.lock()?;
        Ok(map.contains_key(key))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object_store_fs::content_hash;

    #[test]
    fn put_get_exists_round_trip() {
        let store = InMemoryObjectStore::new();
        let bytes = b"hook.wav bytes";
        let key = content_hash(bytes);
        assert!(!store.exists(&key).unwrap());
        store.put(&key, bytes).unwrap();
        assert!(store.exists(&key).unwrap());
        assert_eq!(store.get(&key).unwrap(), bytes);
    }

    #[test]
    fn put_is_immutable() {
        let store = InMemoryObjectStore::new();
        let key = content_hash(b"original");
        store.put(&key, b"original").unwrap();
        // A (hypothetical) second write under the same key does not mutate stored bytes.
        store.put(&key, b"tampered").unwrap();
        assert_eq!(store.get(&key).unwrap(), b"original");
    }
}
