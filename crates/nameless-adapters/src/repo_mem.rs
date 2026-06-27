//! In-memory fragment repository — the RAM-safe fake for state-machine + flow unit tests.
//!
//! Backed by `Mutex<HashMap>`; no DB server needed. The production `PostgresFragmentRepo` (behind
//! the `postgres` feature) satisfies the same [`FragmentRepo`] trait, so any test written against
//! this fake exercises the real call sequence the CLI uses.

use std::collections::HashMap;
use std::sync::Mutex;

use nameless_core::error::RepoError;
use nameless_core::fragment::{Fragment, FragmentId, Project, ProjectId};
use nameless_core::ports::FragmentRepo;

/// An in-memory [`FragmentRepo`].
#[derive(Debug, Default)]
pub struct InMemoryFragmentRepo {
    inner: Mutex<Inner>,
}

#[derive(Debug, Default)]
struct Inner {
    projects: HashMap<ProjectId, Project>,
    fragments: HashMap<FragmentId, Fragment>,
    /// Insertion order of fragments, so `list_fragments` can return newest-first deterministically.
    order: Vec<FragmentId>,
}

impl InMemoryFragmentRepo {
    pub fn new() -> Self {
        Self::default()
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>, RepoError> {
        self.inner
            .lock()
            .map_err(|_| RepoError::Backend("repo mutex poisoned".into()))
    }
}

impl FragmentRepo for InMemoryFragmentRepo {
    fn insert_project(&self, p: &Project) -> Result<(), RepoError> {
        self.lock()?.projects.insert(p.id, p.clone());
        Ok(())
    }

    fn insert_fragment(&self, f: &Fragment) -> Result<(), RepoError> {
        let mut inner = self.lock()?;
        if inner.fragments.insert(f.id, f.clone()).is_none() {
            inner.order.push(f.id);
        }
        Ok(())
    }

    fn list_fragments(&self, project: Option<ProjectId>) -> Result<Vec<Fragment>, RepoError> {
        let inner = self.lock()?;
        // Newest-first (reverse insertion order).
        let out = inner
            .order
            .iter()
            .rev()
            .filter_map(|id| inner.fragments.get(id))
            .filter(|f| project.map(|p| f.project_id == p).unwrap_or(true))
            .cloned()
            .collect();
        Ok(out)
    }

    fn get_fragment(&self, id: FragmentId) -> Result<Option<Fragment>, RepoError> {
        Ok(self.lock()?.fragments.get(&id).cloned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::fragment::FragmentKind;

    #[test]
    fn insert_then_list_and_get() {
        let repo = InMemoryFragmentRepo::new();
        let project = Project::new("demo".into());
        repo.insert_project(&project).unwrap();

        let f1 = Fragment::new_capture(
            project.id,
            FragmentKind::Hook,
            "h1".into(),
            None,
            None,
            "hook".into(),
        );
        let f2 = Fragment::new_capture(
            project.id,
            FragmentKind::Beat,
            "h2".into(),
            None,
            None,
            "beat".into(),
        );
        repo.insert_fragment(&f1).unwrap();
        repo.insert_fragment(&f2).unwrap();

        let all = repo.list_fragments(None).unwrap();
        assert_eq!(all.len(), 2);
        // Newest-first.
        assert_eq!(all[0].id, f2.id);
        assert_eq!(all[1].id, f1.id);

        assert_eq!(repo.get_fragment(f1.id).unwrap().unwrap().id, f1.id);
        assert!(repo
            .get_fragment(FragmentId::new())
            .unwrap()
            .is_none());
    }

    #[test]
    fn list_filters_by_project() {
        let repo = InMemoryFragmentRepo::new();
        let a = Project::new("a".into());
        let b = Project::new("b".into());
        repo.insert_fragment(&Fragment::new_capture(
            a.id,
            FragmentKind::Hook,
            "x".into(),
            None,
            None,
            "n".into(),
        ))
        .unwrap();
        repo.insert_fragment(&Fragment::new_capture(
            b.id,
            FragmentKind::Hook,
            "y".into(),
            None,
            None,
            "n".into(),
        ))
        .unwrap();

        assert_eq!(repo.list_fragments(Some(a.id)).unwrap().len(), 1);
        assert_eq!(repo.list_fragments(Some(b.id)).unwrap().len(), 1);
        assert_eq!(repo.list_fragments(None).unwrap().len(), 2);
    }
}
