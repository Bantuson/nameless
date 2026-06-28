//! In-memory reference store — the RAM-safe fake for Phase-7 unit tests.
//!
//! Backed by `Mutex<HashMap>`; no DB server needed. The production `PostgresReferenceStore` (behind
//! the `postgres` feature) satisfies the same [`ReferenceStore`] trait, so a test written against
//! this fake exercises the real CLI call sequence (`upload` → `attach` → `show`).
//!
//! Like the real plane, this fake separates the two writers: `insert_track`/`attach` are the control
//! plane's job (the CLI calls them), while the `reference_context` is normally written by the Python
//! analyzer. The fake exposes [`InMemoryReferenceStore::set_context`] as a TEST SEAM standing in for
//! that analyzer write, so `get_context_summary` (and `reference show`) can be exercised end-to-end.

use std::collections::HashMap;
use std::sync::Mutex;

use nameless_core::error::RepoError;
use nameless_core::fragment::ProjectId;
use nameless_core::ports::ReferenceStore;
use nameless_core::reference::{
    ProjectReference, ReferenceContext, ReferenceContextSummary, ReferenceRole, ReferenceTrack,
    ReferenceTrackId,
};

/// An in-memory [`ReferenceStore`].
#[derive(Debug, Default)]
pub struct InMemoryReferenceStore {
    inner: Mutex<Inner>,
}

#[derive(Debug, Default)]
struct Inner {
    tracks: HashMap<ReferenceTrackId, ReferenceTrack>,
    /// Insertion order so `list_tracks` can return newest-first deterministically.
    order: Vec<ReferenceTrackId>,
    /// Compact context summaries (the analyzer write, modelled as a test seam).
    contexts: HashMap<ReferenceTrackId, ReferenceContextSummary>,
    /// project → its attached references (with roles). Upsert by reference id.
    links: HashMap<ProjectId, Vec<ProjectReference>>,
}

impl InMemoryReferenceStore {
    pub fn new() -> Self {
        Self::default()
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>, RepoError> {
        self.inner
            .lock()
            .map_err(|_| RepoError::Backend("reference store mutex poisoned".into()))
    }

    /// TEST SEAM: store a context's compact summary (stands in for the Python analyzer's write).
    /// Stores `ctx.summary()` so the embedding vector is dropped exactly as the real read path does.
    pub fn set_context(&self, ctx: &ReferenceContext) -> Result<(), RepoError> {
        self.lock()?
            .contexts
            .insert(ctx.reference_track_id, ctx.summary());
        Ok(())
    }
}

impl ReferenceStore for InMemoryReferenceStore {
    fn insert_track(&self, track: &ReferenceTrack) -> Result<(), RepoError> {
        let mut inner = self.lock()?;
        if inner.tracks.insert(track.id, track.clone()).is_none() {
            inner.order.push(track.id);
        }
        Ok(())
    }

    fn get_track(&self, id: ReferenceTrackId) -> Result<Option<ReferenceTrack>, RepoError> {
        Ok(self.lock()?.tracks.get(&id).cloned())
    }

    fn list_tracks(&self) -> Result<Vec<ReferenceTrack>, RepoError> {
        let inner = self.lock()?;
        let out = inner
            .order
            .iter()
            .rev() // newest-first
            .filter_map(|id| inner.tracks.get(id))
            .cloned()
            .collect();
        Ok(out)
    }

    fn get_context_summary(
        &self,
        id: ReferenceTrackId,
    ) -> Result<Option<ReferenceContextSummary>, RepoError> {
        Ok(self.lock()?.contexts.get(&id).cloned())
    }

    fn attach(
        &self,
        project: ProjectId,
        reference: ReferenceTrackId,
        role: ReferenceRole,
    ) -> Result<(), RepoError> {
        let mut inner = self.lock()?;
        let links = inner.links.entry(project).or_default();
        // Upsert on the (project, reference) composite key — re-attach updates the role.
        if let Some(existing) = links
            .iter_mut()
            .find(|l| l.reference_track_id == reference)
        {
            existing.role = role;
        } else {
            links.push(ProjectReference {
                reference_track_id: reference,
                role,
            });
        }
        Ok(())
    }

    fn list_project_references(
        &self,
        project: ProjectId,
    ) -> Result<Vec<ProjectReference>, RepoError> {
        Ok(self
            .lock()?
            .links
            .get(&project)
            .cloned()
            .unwrap_or_default())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::reference::TonalBalance;

    fn ctx(id: ReferenceTrackId) -> ReferenceContext {
        ReferenceContext {
            reference_track_id: id,
            clap_style_embedding: vec![0.1; 512],
            genre: Some("amapiano".into()),
            tempo_bpm_min: 110.0,
            tempo_bpm_max: 116.0,
            lufs: -9.0,
            tonal_balance: TonalBalance {
                low: 0.3,
                low_mid: 0.25,
                mid: 0.2,
                high_mid: 0.15,
                high: 0.1,
            },
            stereo_width: 0.4,
            vibe_description: "warm late-night".into(),
            analyzer_version: "fake-ref-0".into(),
        }
    }

    #[test]
    fn insert_get_list_round_trip_newest_first() {
        let store = InMemoryReferenceStore::new();
        let t1 = ReferenceTrack::new_upload("a".into(), None, None, None, None);
        let t2 = ReferenceTrack::new_upload("b".into(), None, None, None, None);
        store.insert_track(&t1).unwrap();
        store.insert_track(&t2).unwrap();

        let all = store.list_tracks().unwrap();
        assert_eq!(all.len(), 2);
        assert_eq!(all[0].id, t2.id); // newest-first
        assert_eq!(store.get_track(t1.id).unwrap().unwrap().id, t1.id);
        assert!(store.get_track(ReferenceTrackId::new()).unwrap().is_none());
    }

    #[test]
    fn context_summary_is_none_until_analyzed_then_array_free() {
        let store = InMemoryReferenceStore::new();
        let t = ReferenceTrack::new_upload("a".into(), None, None, None, None);
        store.insert_track(&t).unwrap();
        // Not analyzed yet.
        assert!(store.get_context_summary(t.id).unwrap().is_none());
        // Analyzer writes context (test seam) → summary readable, embedding dropped to a dim.
        store.set_context(&ctx(t.id)).unwrap();
        let s = store.get_context_summary(t.id).unwrap().unwrap();
        assert_eq!(s.embedding_dim, 512);
        assert_eq!(s.genre.as_deref(), Some("amapiano"));
    }

    #[test]
    fn attach_is_idempotent_and_updates_role() {
        let store = InMemoryReferenceStore::new();
        let project = ProjectId::new();
        let t = ReferenceTrack::new_upload("a".into(), None, None, None, None);
        store.insert_track(&t).unwrap();

        store.attach(project, t.id, ReferenceRole::Vibe).unwrap();
        store
            .attach(project, t.id, ReferenceRole::SonicTarget)
            .unwrap();

        let links = store.list_project_references(project).unwrap();
        // Re-attach upserts on the composite key (no duplicate), role updated to the latest.
        assert_eq!(links.len(), 1);
        assert_eq!(links[0].reference_track_id, t.id);
        assert_eq!(links[0].role, ReferenceRole::SonicTarget);
        // A different project sees no links.
        assert!(store
            .list_project_references(ProjectId::new())
            .unwrap()
            .is_empty());
    }
}
