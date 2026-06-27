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
}

impl FileFragmentRepo {
    /// Open (or lazily create) a repo at `path`. The file is created on first write.
    pub fn new(path: impl Into<PathBuf>) -> Self {
        FileFragmentRepo { path: path.into() }
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

    fn insert_fragment(&self, f: &Fragment) -> Result<(), RepoError> {
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
}
