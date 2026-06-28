//! File-backed fragment repository — the `--local` persistence layer.
//!
//! Persists the whole graph (projects + fragments) as a single `serde_json` document on disk via
//! a read-modify-write cycle. This is what lets `nameless --local capture …` in one process and
//! `nameless --local fragments list` in a *separate* process see the same row — the walking
//! skeleton runs with NO Postgres on the 4GB box.
//!
//! A JSON document (rather than SQLite) is a deliberate choice: it keeps the default build pure
//! sync-Rust with no native/driver dependency, which is exactly what keeps the lean build buildable
//! within 4GB. The trade-off — whole-file rewrite per insert, no concurrent writers — is fine for a
//! single-user local CLI. The production path uses `PostgresFragmentRepo` instead.

use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use nameless_core::error::RepoError;
use nameless_core::fragment::{Fragment, FragmentId, Project, ProjectId};
use nameless_core::ports::FragmentRepo;

/// The on-disk document shape. Versioned so a future migration can detect old files.
#[derive(Debug, Default, Serialize, Deserialize)]
struct Db {
    #[serde(default)]
    version: u32,
    #[serde(default)]
    projects: Vec<Project>,
    #[serde(default)]
    fragments: Vec<Fragment>,
}

const DB_VERSION: u32 = 1;

/// A [`FragmentRepo`] persisted to a single JSON file.
#[derive(Debug, Clone)]
pub struct FileFragmentRepo {
    path: PathBuf,
    /// Serializes the whole `load → mutate → store` critical section of every mutating method.
    ///
    /// Until Phase 10 this store only ever ran one-operation-per-process (the `nameless` CLI), so a
    /// read-modify-write needed no lock. The axum control plane shares ONE `Arc<Plane>` (hence one
    /// store instance) across multi-threaded worker threads and dispatches writes through
    /// `spawn_blocking`, so two concurrent `POST`s could otherwise both `load()`, each append a
    /// different row, and each `store()` — the second atomic rename silently dropping the first
    /// write (WR-01). Holding this lock across the read+mutate+write makes the cycle a critical
    /// section. `Arc<Mutex<_>>` so `Clone`d handles to the same store share one lock (the in-memory
    /// adapters already lock per op — this brings the file ones to parity).
    write_lock: Arc<Mutex<()>>,
}

impl FileFragmentRepo {
    /// Open (or lazily create) a repo at `path`. The file is created on first write.
    pub fn new(path: impl Into<PathBuf>) -> Self {
        FileFragmentRepo {
            path: path.into(),
            write_lock: Arc::new(Mutex::new(())),
        }
    }

    /// Acquire the write-serialization guard, recovering from a poisoned lock.
    ///
    /// Poisoning means a previous writer panicked mid-mutation; the on-disk file is still intact
    /// (the temp-file + atomic rename guarantees that), so recovering the guard and letting the next
    /// writer proceed is safe and avoids bricking all future writes.
    fn write_guard(&self) -> std::sync::MutexGuard<'_, ()> {
        self.write_lock.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Load the document, treating a missing file as an empty db.
    fn load(&self) -> Result<Db, RepoError> {
        match fs::read(&self.path) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map_err(|e| RepoError::Serialization(e.to_string())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Db {
                version: DB_VERSION,
                ..Default::default()
            }),
            Err(e) => Err(RepoError::Io(e.to_string())),
        }
    }

    /// Atomically write the document (temp file + rename) so a crash can't truncate the db.
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

impl FragmentRepo for FileFragmentRepo {
    fn insert_project(&self, p: &Project) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        db.version = DB_VERSION;
        // Upsert by id (idempotent re-insert).
        if let Some(existing) = db.projects.iter_mut().find(|x| x.id == p.id) {
            *existing = p.clone();
        } else {
            db.projects.push(p.clone());
        }
        self.store(&db)
    }

    fn list_projects(&self) -> Result<Vec<Project>, RepoError> {
        let db = self.load()?;
        // Newest-first by creation time (stored order is insertion order; sort explicitly).
        let mut out = db.projects;
        out.sort_by(|a, b| b.created_at_ms.cmp(&a.created_at_ms));
        Ok(out)
    }

    fn get_project(&self, id: ProjectId) -> Result<Option<Project>, RepoError> {
        let db = self.load()?;
        Ok(db.projects.into_iter().find(|p| p.id == id))
    }

    fn insert_fragment(&self, f: &Fragment) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        db.version = DB_VERSION;
        if let Some(existing) = db.fragments.iter_mut().find(|x| x.id == f.id) {
            *existing = f.clone();
        } else {
            db.fragments.push(f.clone());
        }
        self.store(&db)
    }

    fn list_fragments(&self, project: Option<ProjectId>) -> Result<Vec<Fragment>, RepoError> {
        let db = self.load()?;
        // Newest-first (reverse stored order).
        let out = db
            .fragments
            .into_iter()
            .rev()
            .filter(|f| project.map(|p| f.project_id == p).unwrap_or(true))
            .collect();
        Ok(out)
    }

    fn get_fragment(&self, id: FragmentId) -> Result<Option<Fragment>, RepoError> {
        let db = self.load()?;
        Ok(db.fragments.into_iter().find(|f| f.id == id))
    }

    fn delete_fragment(&self, id: FragmentId) -> Result<(), RepoError> {
        let _guard = self.write_guard(); // serialize the load→mutate→store cycle (WR-01)
        let mut db = self.load()?;
        let before = db.fragments.len();
        db.fragments.retain(|f| f.id != id);
        // Only rewrite the file when something actually changed (idempotent on a missing id).
        if db.fragments.len() != before {
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
    use nameless_core::fragment::FragmentKind;
    use std::env;

    fn temp_db(tag: &str) -> PathBuf {
        let mut p = env::temp_dir();
        p.push(format!(
            "nameless-filerepo-{tag}-{}.json",
            content_hash(format!("{:?}{tag}", std::time::SystemTime::now()).as_bytes())
        ));
        p
    }

    #[test]
    fn persists_across_new_instances() {
        let path = temp_db("persist");
        let project = Project::new("demo".into());
        let frag = Fragment::new_capture(
            project.id,
            FragmentKind::Hook,
            "abc".into(),
            Some(1000),
            Some(44_100),
            "chorus hook".into(),
        );

        // First "process": write.
        {
            let repo = FileFragmentRepo::new(&path);
            repo.insert_project(&project).unwrap();
            repo.insert_fragment(&frag).unwrap();
        }
        // Second "process": a brand-new instance over the same path reads it back.
        {
            let repo = FileFragmentRepo::new(&path);
            let all = repo.list_fragments(None).unwrap();
            assert_eq!(all.len(), 1);
            assert_eq!(all[0].id, frag.id);
            assert_eq!(all[0].note_text, "chorus hook");
            assert_eq!(repo.get_fragment(frag.id).unwrap().unwrap().id, frag.id);
        }

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn missing_file_is_empty_db() {
        let path = temp_db("absent");
        let repo = FileFragmentRepo::new(&path);
        assert_eq!(repo.list_fragments(None).unwrap().len(), 0);
    }

    #[test]
    fn projects_persist_and_are_listable_and_gettable() {
        let path = temp_db("projects");
        let a = Project::new("a".into());
        let b = Project::new("b".into());
        {
            let repo = FileFragmentRepo::new(&path);
            repo.insert_project(&a).unwrap();
            repo.insert_project(&b).unwrap();
        }
        // A fresh instance over the same file reads both back.
        let repo = FileFragmentRepo::new(&path);
        assert_eq!(repo.list_projects().unwrap().len(), 2);
        assert_eq!(repo.get_project(b.id).unwrap().unwrap().title, "b");
        assert!(repo.get_project(ProjectId::new()).unwrap().is_none());
        let _ = fs::remove_file(&path);
    }
}
