//! In-memory stem + attribution store — the RAM-safe fake for Phase-8 unit tests.
//!
//! Backed by `Mutex<HashMap>`; no DB server needed. One object implements BOTH [`StemStore`] and
//! [`AttributionStore`] (hence [`nameless_core::ports::SampleStore`]), because the production
//! Postgres adapter backs both with one database — so a test written against this fake exercises the
//! real `stems separate` → `stems list` → `sample add` → `credits` call sequence with only the DB
//! swapped.

use std::collections::HashMap;
use std::sync::Mutex;

use nameless_core::attribution::SampleAttribution;
use nameless_core::error::RepoError;
use nameless_core::fragment::{FragmentId, ProjectId};
use nameless_core::ports::{AttributionStore, StemStore};
use nameless_core::reference::ReferenceTrackId;
use nameless_core::stems::{Stem, StemId};

/// An in-memory [`StemStore`] + [`AttributionStore`].
#[derive(Debug, Default)]
pub struct InMemorySampleStore {
    inner: Mutex<Inner>,
}

#[derive(Debug, Default)]
struct Inner {
    stems: HashMap<StemId, Stem>,
    /// Insertion order so `list_stems` can return newest-first deterministically.
    stem_order: Vec<StemId>,
    attributions: HashMap<FragmentId, SampleAttribution>,
}

impl InMemorySampleStore {
    pub fn new() -> Self {
        Self::default()
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>, RepoError> {
        self.inner
            .lock()
            .map_err(|_| RepoError::Backend("sample store mutex poisoned".into()))
    }
}

impl StemStore for InMemorySampleStore {
    fn insert_stem(&self, stem: &Stem) -> Result<(), RepoError> {
        let mut inner = self.lock()?;
        if inner.stems.insert(stem.id, stem.clone()).is_none() {
            inner.stem_order.push(stem.id);
        }
        Ok(())
    }

    fn get_stem(&self, id: StemId) -> Result<Option<Stem>, RepoError> {
        Ok(self.lock()?.stems.get(&id).cloned())
    }

    fn list_stems(&self, track: ReferenceTrackId) -> Result<Vec<Stem>, RepoError> {
        let inner = self.lock()?;
        let out = inner
            .stem_order
            .iter()
            .rev() // newest-first
            .filter_map(|id| inner.stems.get(id))
            .filter(|s| s.reference_track_id == track)
            .cloned()
            .collect();
        Ok(out)
    }
}

impl AttributionStore for InMemorySampleStore {
    fn insert_attribution(&self, attribution: &SampleAttribution) -> Result<(), RepoError> {
        self.lock()?
            .attributions
            .insert(attribution.fragment_id, attribution.clone());
        Ok(())
    }

    fn get_attribution(
        &self,
        fragment: FragmentId,
    ) -> Result<Option<SampleAttribution>, RepoError> {
        Ok(self.lock()?.attributions.get(&fragment).cloned())
    }

    fn list_project_attributions(
        &self,
        project: ProjectId,
    ) -> Result<Vec<SampleAttribution>, RepoError> {
        Ok(self
            .lock()?
            .attributions
            .values()
            .filter(|a| a.project_id == project)
            .cloned()
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::attribution::{CompleteAttribution, PartialAttribution, RightsStatus};
    use nameless_core::stems::StemType;

    fn stem(track: ReferenceTrackId, st: StemType) -> Stem {
        Stem::new(
            track,
            st,
            format!("uri-{}", st.as_str()),
            "htdemucs_ft".into(),
            "4.0.1".into(),
            Some(210_000),
            Some(44_100),
        )
    }

    fn complete(track: ReferenceTrackId, stem_id: StemId) -> CompleteAttribution {
        PartialAttribution {
            source_track_id: Some(track),
            stem_id: Some(stem_id),
            source_title: Some("Trust".into()),
            source_artist: Some("Brent Faiyaz".into()),
            stem_type: Some(StemType::Vocals),
            start_ms: Some(12_000),
            end_ms: Some(18_000),
            rights_status: Some(RightsStatus::CopyrightedUncleared),
        }
        .into_complete()
        .unwrap()
    }

    #[test]
    fn stems_are_listed_per_track_newest_first() {
        let store = InMemorySampleStore::new();
        let track_a = ReferenceTrackId::new();
        let track_b = ReferenceTrackId::new();
        let s1 = stem(track_a, StemType::Vocals);
        let s2 = stem(track_a, StemType::Bass);
        let s3 = stem(track_b, StemType::Drums);
        store.insert_stem(&s1).unwrap();
        store.insert_stem(&s2).unwrap();
        store.insert_stem(&s3).unwrap();

        let a = store.list_stems(track_a).unwrap();
        assert_eq!(a.len(), 2);
        assert_eq!(a[0].id, s2.id); // newest-first
        assert_eq!(store.get_stem(s1.id).unwrap().unwrap().id, s1.id);
        // track_b sees only its own stem.
        assert_eq!(store.list_stems(track_b).unwrap().len(), 1);
    }

    #[test]
    fn attributions_are_listed_per_project() {
        let store = InMemorySampleStore::new();
        let project = ProjectId::new();
        let other = ProjectId::new();
        let track = ReferenceTrackId::new();
        let s = stem(track, StemType::Vocals);
        store.insert_stem(&s).unwrap();

        let frag = FragmentId::new();
        let attr = SampleAttribution::new(frag, project, complete(track, s.id));
        store.insert_attribution(&attr).unwrap();

        assert_eq!(store.get_attribution(frag).unwrap().unwrap(), attr);
        assert_eq!(store.list_project_attributions(project).unwrap().len(), 1);
        assert!(store.list_project_attributions(other).unwrap().is_empty());
    }
}
