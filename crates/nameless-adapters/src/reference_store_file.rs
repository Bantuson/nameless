//! File-backed reference store — the `--local` persistence layer for Phase-7 references.
//!
//! Persists reference tracks, their compact context summaries, and project links as one
//! `serde_json` document, via a read-modify-write cycle — exactly the pattern `FileFragmentRepo`
//! uses, and for the same reason: it keeps the default build pure sync-Rust with no DB driver, so
//! `nameless --local reference upload …` in one process and `reference show …` in another see the
//! same row on the 4GB box.
//!
//! NOTE on the analyzer write: in production the Python `RestrictedReferenceAnalyzer` writes
//! `reference_context` to Postgres. For the local/no-Postgres profile there is no worker, so this
//! store exposes [`FileReferenceStore::set_context_summary`] (used by tests / a future local
//! analyzer shim). `reference upload --local` persists the track + enqueues the job; the context is
//! filled by that local analyzer path, mirroring the server flow with the heavy leaf swapped.

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use nameless_core::error::RepoError;
use nameless_core::fragment::ProjectId;
use nameless_core::ports::ReferenceStore;
use nameless_core::reference::{
    ProjectReference, ReferenceContext, ReferenceContextSummary, ReferenceRole, ReferenceTrack,
    ReferenceTrackId,
};

/// One project→reference link row, persisted flat for easy JSON round-tripping.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct LinkRow {
    project_id: ProjectId,
    reference_track_id: ReferenceTrackId,
    role: ReferenceRole,
}

/// The on-disk document shape. Versioned so a future migration can detect old files.
#[derive(Debug, Default, Serialize, Deserialize)]
struct Db {
    #[serde(default)]
    version: u32,
    #[serde(default)]
    tracks: Vec<ReferenceTrack>,
    #[serde(default)]
    contexts: Vec<ReferenceContextSummary>,
    #[serde(default)]
    links: Vec<LinkRow>,
}

const DB_VERSION: u32 = 1;

/// A [`ReferenceStore`] persisted to a single JSON file.
#[derive(Debug, Clone)]
pub struct FileReferenceStore {
    path: PathBuf,
}

impl FileReferenceStore {
    /// Open (or lazily create) a store at `path`. The file is created on first write.
    pub fn new(path: impl Into<PathBuf>) -> Self {
        FileReferenceStore { path: path.into() }
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

    /// Persist a context's compact summary (the local stand-in for the Python analyzer write).
    /// Stores `ctx.summary()` so the embedding vector never lands on disk in the readable surface.
    pub fn set_context_summary(&self, ctx: &ReferenceContext) -> Result<(), RepoError> {
        let mut db = self.load()?;
        db.version = DB_VERSION;
        let summary = ctx.summary();
        if let Some(existing) = db
            .contexts
            .iter_mut()
            .find(|c| c.reference_track_id == summary.reference_track_id)
        {
            *existing = summary;
        } else {
            db.contexts.push(summary);
        }
        self.store(&db)
    }
}

impl ReferenceStore for FileReferenceStore {
    fn insert_track(&self, track: &ReferenceTrack) -> Result<(), RepoError> {
        let mut db = self.load()?;
        db.version = DB_VERSION;
        if let Some(existing) = db.tracks.iter_mut().find(|t| t.id == track.id) {
            *existing = track.clone();
        } else {
            db.tracks.push(track.clone());
        }
        self.store(&db)
    }

    fn get_track(&self, id: ReferenceTrackId) -> Result<Option<ReferenceTrack>, RepoError> {
        Ok(self.load()?.tracks.into_iter().find(|t| t.id == id))
    }

    fn list_tracks(&self) -> Result<Vec<ReferenceTrack>, RepoError> {
        let db = self.load()?;
        Ok(db.tracks.into_iter().rev().collect()) // newest-first
    }

    fn get_context_summary(
        &self,
        id: ReferenceTrackId,
    ) -> Result<Option<ReferenceContextSummary>, RepoError> {
        Ok(self
            .load()?
            .contexts
            .into_iter()
            .find(|c| c.reference_track_id == id))
    }

    fn attach(
        &self,
        project: ProjectId,
        reference: ReferenceTrackId,
        role: ReferenceRole,
    ) -> Result<(), RepoError> {
        let mut db = self.load()?;
        db.version = DB_VERSION;
        if let Some(existing) = db
            .links
            .iter_mut()
            .find(|l| l.project_id == project && l.reference_track_id == reference)
        {
            existing.role = role;
        } else {
            db.links.push(LinkRow {
                project_id: project,
                reference_track_id: reference,
                role,
            });
        }
        self.store(&db)
    }

    fn list_project_references(
        &self,
        project: ProjectId,
    ) -> Result<Vec<ProjectReference>, RepoError> {
        let db = self.load()?;
        Ok(db
            .links
            .into_iter()
            .filter(|l| l.project_id == project)
            .map(|l| ProjectReference {
                reference_track_id: l.reference_track_id,
                role: l.role,
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object_store_fs::content_hash;
    use nameless_core::reference::TonalBalance;
    use std::env;

    fn temp_db(tag: &str) -> PathBuf {
        let mut p = env::temp_dir();
        p.push(format!(
            "nameless-reffile-{tag}-{}.json",
            content_hash(format!("{:?}{tag}", std::time::SystemTime::now()).as_bytes())
        ));
        p
    }

    #[test]
    fn persists_track_context_and_link_across_instances() {
        let path = temp_db("persist");
        let track = ReferenceTrack::new_upload("abc".into(), Some("T".into()), None, None, None);
        let project = ProjectId::new();
        let ctx = ReferenceContext {
            reference_track_id: track.id,
            clap_style_embedding: vec![0.2; 512],
            genre: Some("deep-house".into()),
            tempo_bpm_min: 120.0,
            tempo_bpm_max: 124.0,
            lufs: -8.0,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.55,
            vibe_description: "deep, hypnotic".into(),
            analyzer_version: "fake-ref-0".into(),
        };

        // First "process": write track + context + link.
        {
            let store = FileReferenceStore::new(&path);
            store.insert_track(&track).unwrap();
            store.set_context_summary(&ctx).unwrap();
            store
                .attach(project, track.id, ReferenceRole::SonicTarget)
                .unwrap();
        }
        // Second "process": a fresh instance reads it all back.
        {
            let store = FileReferenceStore::new(&path);
            assert_eq!(store.list_tracks().unwrap().len(), 1);
            let s = store.get_context_summary(track.id).unwrap().unwrap();
            assert_eq!(s.embedding_dim, 512);
            assert_eq!(s.genre.as_deref(), Some("deep-house"));
            let links = store.list_project_references(project).unwrap();
            assert_eq!(links.len(), 1);
            assert_eq!(links[0].role, ReferenceRole::SonicTarget);
        }

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn missing_file_is_empty_store() {
        let store = FileReferenceStore::new(temp_db("absent"));
        assert_eq!(store.list_tracks().unwrap().len(), 0);
    }
}
