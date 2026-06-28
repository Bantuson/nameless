//! File-backed stem + attribution store — the `--local` persistence layer for Phase-8 sampling.
//!
//! Persists the stem library + sample attributions as one `serde_json` document via a
//! read-modify-write cycle — exactly the pattern `FileReferenceStore` uses, and for the same reason:
//! it keeps the default build pure sync-Rust with no DB driver, so `nameless --local stems separate`
//! (worker-driven), `stems list`, `sample add`, and `credits` across separate process invocations all
//! see the same rows on the 4GB box.
//!
//! One struct implements BOTH [`StemStore`] and [`AttributionStore`] (hence
//! [`nameless_core::ports::SampleStore`]), so the `--local` profile can hold a single store object.

use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use nameless_core::attribution::SampleAttribution;
use nameless_core::error::RepoError;
use nameless_core::fragment::{FragmentId, ProjectId};
use nameless_core::ports::{AttributionStore, StemStore};
use nameless_core::reference::ReferenceTrackId;
use nameless_core::stems::{Stem, StemId};

/// The on-disk document shape. Versioned so a future migration can detect old files.
#[derive(Debug, Default, Serialize, Deserialize)]
struct Db {
    #[serde(default)]
    version: u32,
    #[serde(default)]
    stems: Vec<Stem>,
    #[serde(default)]
    attributions: Vec<SampleAttribution>,
}

const DB_VERSION: u32 = 1;

/// A [`StemStore`] + [`AttributionStore`] persisted to a single JSON file.
#[derive(Debug, Clone)]
pub struct FileSampleStore {
    path: PathBuf,
    /// Serializes the `load → mutate → store` critical section of every mutating method (across
    /// BOTH the `StemStore` and `AttributionStore` impls — they share one file) so the concurrent
    /// axum control plane cannot interleave two read-modify-writes and silently drop one (WR-01).
    /// `Arc<Mutex<_>>` so clones share one lock; matches the in-memory adapters' per-op locking.
    write_lock: Arc<Mutex<()>>,
}

impl FileSampleStore {
    /// Open (or lazily create) a store at `path`. The file is created on first write.
    pub fn new(path: impl Into<PathBuf>) -> Self {
        FileSampleStore {
            path: path.into(),
            write_lock: Arc::new(Mutex::new(())),
        }
    }

    /// Acquire the write-serialization guard, recovering from a poisoned lock (the atomic
    /// temp-file+rename keeps the on-disk file intact even if a prior writer panicked).
    fn write_guard(&self) -> std::sync::MutexGuard<'_, ()> {
        self.write_lock.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn load(&self) -> Result<Db, RepoError> {
        match fs::read(&self.path) {
            Ok(bytes) => {
                serde_json::from_slice(&bytes).map_err(|e| RepoError::Serialization(e.to_string()))
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Db {
                version: DB_VERSION,
                ..Default::default()
            }),
            Err(e) => Err(RepoError::Io(e.to_string())),
        }
    }

    fn store(&self, db: &Db) -> Result<(), RepoError> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).map_err(|e| RepoError::Io(e.to_string()))?;
        }
        let bytes =
            serde_json::to_vec_pretty(db).map_err(|e| RepoError::Serialization(e.to_string()))?;
        let tmp = self.path.with_extension("json.tmp");
        fs::write(&tmp, &bytes).map_err(|e| RepoError::Io(e.to_string()))?;
        fs::rename(&tmp, &self.path).map_err(|e| RepoError::Io(e.to_string()))?;
        Ok(())
    }
}

impl StemStore for FileSampleStore {
    fn insert_stem(&self, stem: &Stem) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        db.version = DB_VERSION;
        if let Some(existing) = db.stems.iter_mut().find(|s| s.id == stem.id) {
            *existing = stem.clone();
        } else {
            db.stems.push(stem.clone());
        }
        self.store(&db)
    }

    fn get_stem(&self, id: StemId) -> Result<Option<Stem>, RepoError> {
        Ok(self.load()?.stems.into_iter().find(|s| s.id == id))
    }

    fn list_stems(&self, track: ReferenceTrackId) -> Result<Vec<Stem>, RepoError> {
        let db = self.load()?;
        Ok(db
            .stems
            .into_iter()
            .rev() // newest-first
            .filter(|s| s.reference_track_id == track)
            .collect())
    }
}

impl AttributionStore for FileSampleStore {
    fn insert_attribution(&self, attribution: &SampleAttribution) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        db.version = DB_VERSION;
        if let Some(existing) = db
            .attributions
            .iter_mut()
            .find(|a| a.fragment_id == attribution.fragment_id)
        {
            *existing = attribution.clone();
        } else {
            db.attributions.push(attribution.clone());
        }
        self.store(&db)
    }

    fn get_attribution(
        &self,
        fragment: FragmentId,
    ) -> Result<Option<SampleAttribution>, RepoError> {
        Ok(self
            .load()?
            .attributions
            .into_iter()
            .find(|a| a.fragment_id == fragment))
    }

    fn list_project_attributions(
        &self,
        project: ProjectId,
    ) -> Result<Vec<SampleAttribution>, RepoError> {
        let db = self.load()?;
        Ok(db
            .attributions
            .into_iter()
            .filter(|a| a.project_id == project)
            .collect())
    }

    fn delete_attribution(&self, fragment: FragmentId) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        let before = db.attributions.len();
        db.attributions.retain(|a| a.fragment_id != fragment);
        // Only rewrite when something changed (idempotent on a missing row).
        if db.attributions.len() != before {
            db.version = DB_VERSION;
            self.store(&db)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object_store_fs::content_hash;
    use nameless_core::attribution::{PartialAttribution, RightsStatus};
    use nameless_core::stems::StemType;
    use std::env;

    fn temp_db(tag: &str) -> PathBuf {
        let mut p = env::temp_dir();
        p.push(format!(
            "nameless-samplefile-{tag}-{}.json",
            content_hash(format!("{:?}{tag}", std::time::SystemTime::now()).as_bytes())
        ));
        p
    }

    #[test]
    fn persists_stems_and_attribution_across_instances() {
        let path = temp_db("persist");
        let track = ReferenceTrackId::new();
        let project = ProjectId::new();
        let stem = Stem::new(
            track,
            StemType::Piano,
            "stemuri".into(),
            "htdemucs_6s".into(),
            "4.0.1".into(),
            Some(180_000),
            Some(44_100),
        );
        let frag = FragmentId::new();
        let attr = SampleAttribution::new(
            frag,
            project,
            PartialAttribution {
                source_track_id: Some(track),
                stem_id: Some(stem.id),
                source_title: Some("Alt Piano Loop".into()),
                source_artist: Some("Ben Produces".into()),
                stem_type: Some(StemType::Piano),
                start_ms: Some(0),
                end_ms: Some(8_000),
                rights_status: Some(RightsStatus::Unknown),
            }
            .into_complete()
            .unwrap(),
        );

        // First "process": write a stem + an attribution.
        {
            let store = FileSampleStore::new(&path);
            store.insert_stem(&stem).unwrap();
            store.insert_attribution(&attr).unwrap();
        }
        // Second "process": a fresh instance reads it all back.
        {
            let store = FileSampleStore::new(&path);
            assert_eq!(store.list_stems(track).unwrap().len(), 1);
            assert_eq!(store.get_stem(stem.id).unwrap().unwrap().stem_type, StemType::Piano);
            let got = store.get_attribution(frag).unwrap().unwrap();
            assert_eq!(got.attribution.source_artist, "Ben Produces");
            assert_eq!(store.list_project_attributions(project).unwrap().len(), 1);
        }

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn missing_file_is_empty_store() {
        let store = FileSampleStore::new(temp_db("absent"));
        assert_eq!(store.list_stems(ReferenceTrackId::new()).unwrap().len(), 0);
        assert!(store.get_attribution(FragmentId::new()).unwrap().is_none());
    }
}
