//! Production fragment repository on Postgres (sqlx) — behind the `postgres` feature.
//!
//! ## Compile-time-checked SQL
//!
//! Queries use sqlx's `query!` macro: the SQL is verified against the live schema at COMPILE time
//! (parameterized — no string-built SQL, so injection is structurally impossible, T-04-02). That
//! means building with `--features postgres` needs either `DATABASE_URL` pointing at a migrated
//! database, or an offline cache (`cargo sqlx prepare` + `SQLX_OFFLINE=true`). The README documents
//! both paths.
//!
//! ## Sync trait over an async driver (the blocking shim)
//!
//! `FragmentRepo` is synchronous (so the lean `--local` build needs no async runtime). sqlx is
//! async. This adapter bridges the two by owning a Tokio runtime and `block_on`-ing each query at
//! the boundary. The async-ness never leaks into the core or the default build — it is contained
//! entirely here, behind the feature gate. At CLI scale (one operation per process) the cost is
//! irrelevant; the win is one port shape for both the local and production worlds.
//!
//! ## Enum mapping without polluting the core
//!
//! The core `Provenance`/`FragmentState` enums deliberately do NOT derive `sqlx::Type` (that would
//! drag sqlx into the lean default build). Instead we map through their canonical snake_case
//! labels: on write we bind the `&str` label and cast `text → enum` in SQL (`$n::text::provenance`);
//! on read we project the enum back to text (`provenance::text`) and parse with `from_db_str`. The
//! cast is still fully compile-time-checked against the schema.

use std::sync::Arc;

use sqlx::postgres::{PgPool, PgPoolOptions};
use tokio::runtime::Runtime;

use nameless_core::error::RepoError;
use nameless_core::fragment::{Fragment, FragmentId, FragmentKind, Project, ProjectId};
use nameless_core::ports::FragmentRepo;
use nameless_core::provenance::Provenance;
use nameless_core::state_machine::FragmentState;

/// A [`FragmentRepo`] backed by Postgres.
pub struct PostgresFragmentRepo {
    rt: Arc<Runtime>,
    pool: PgPool,
}

impl PostgresFragmentRepo {
    /// Connect using a fresh owned runtime + pool. Convenience for the CLI server profile.
    pub fn connect(database_url: &str) -> Result<Self, RepoError> {
        let rt = Arc::new(Runtime::new().map_err(|e| RepoError::Io(e.to_string()))?);
        let pool = rt
            .block_on(async {
                PgPoolOptions::new()
                    .max_connections(5)
                    .connect(database_url)
                    .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(Self { rt, pool })
    }

    /// Construct from a shared runtime + an already-built pool (lets the server profile share one
    /// runtime across the repo, queue, and store).
    pub fn new(rt: Arc<Runtime>, pool: PgPool) -> Self {
        Self { rt, pool }
    }

    /// Borrow the runtime handle so sibling adapters can share it.
    pub fn runtime(&self) -> Arc<Runtime> {
        Arc::clone(&self.rt)
    }

    /// Reassemble a domain [`Fragment`] from raw row columns (enum labels arrive as text).
    #[allow(clippy::too_many_arguments)]
    fn row_to_fragment(
        id: uuid::Uuid,
        project_id: uuid::Uuid,
        kind: String,
        provenance: String,
        audio_uri: String,
        duration_ms: Option<i32>,
        sample_rate: Option<i32>,
        note_text: String,
        state: String,
        parent_fragment_id: Option<uuid::Uuid>,
        created_at_ms: i64,
    ) -> Result<Fragment, RepoError> {
        let kind = FragmentKind::from_db_str(&kind)
            .ok_or_else(|| RepoError::Serialization(format!("unknown fragment kind: {kind}")))?;
        let provenance = Provenance::from_db_str(&provenance).ok_or_else(|| {
            RepoError::Serialization(format!("unknown provenance: {provenance}"))
        })?;
        let state = FragmentState::from_db_str(&state)
            .ok_or_else(|| RepoError::Serialization(format!("unknown fragment state: {state}")))?;
        Ok(Fragment {
            id: FragmentId(id),
            project_id: ProjectId(project_id),
            kind,
            provenance,
            audio_uri,
            duration_ms: duration_ms.map(|v| v as u32),
            sample_rate: sample_rate.map(|v| v as u32),
            note_text,
            state,
            parent_fragment_id: parent_fragment_id.map(FragmentId),
            created_at_ms,
        })
    }
}

impl FragmentRepo for PostgresFragmentRepo {
    fn insert_project(&self, p: &Project) -> Result<(), RepoError> {
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"insert into projects (id, title, created_at_ms) values ($1, $2, $3)"#,
                    p.id.0,
                    p.title,
                    p.created_at_ms,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn insert_fragment(&self, f: &Fragment) -> Result<(), RepoError> {
        // Bind enum labels as text and cast text→enum in SQL (compile-time-checked, injection-safe).
        let provenance = f.provenance.as_str();
        let state = f.state.as_str();
        let kind = f.kind.as_str();
        let duration = f.duration_ms.map(|v| v as i32);
        let sample_rate = f.sample_rate.map(|v| v as i32);
        let parent = f.parent_fragment_id.map(|p| p.0);

        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    insert into fragments
                        (id, project_id, kind, provenance, audio_uri, duration_ms, sample_rate,
                         note_text, state, parent_fragment_id, created_at_ms)
                    values
                        ($1, $2, $3, $4::text::provenance, $5, $6, $7, $8,
                         $9::text::fragment_state, $10, $11)
                    "#,
                    f.id.0,
                    f.project_id.0,
                    kind,
                    provenance,
                    f.audio_uri,
                    duration,
                    sample_rate,
                    f.note_text,
                    state,
                    parent,
                    f.created_at_ms,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn list_fragments(&self, project: Option<ProjectId>) -> Result<Vec<Fragment>, RepoError> {
        let project_uuid = project.map(|p| p.0);
        let rows = self
            .rt
            .block_on(async {
                // `$1 is null or project_id = $1` keeps it a single compile-checked query for both
                // the filtered and unfiltered cases.
                sqlx::query!(
                    r#"
                    select
                        id,
                        project_id,
                        kind,
                        provenance::text as "provenance!",
                        audio_uri,
                        duration_ms,
                        sample_rate,
                        note_text,
                        state::text as "state!",
                        parent_fragment_id,
                        created_at_ms
                    from fragments
                    where $1::uuid is null or project_id = $1
                    order by created_at_ms desc
                    "#,
                    project_uuid,
                )
                .fetch_all(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        rows.into_iter()
            .map(|r| {
                Self::row_to_fragment(
                    r.id,
                    r.project_id,
                    r.kind,
                    r.provenance,
                    r.audio_uri,
                    r.duration_ms,
                    r.sample_rate,
                    r.note_text,
                    r.state,
                    r.parent_fragment_id,
                    r.created_at_ms,
                )
            })
            .collect()
    }

    fn get_fragment(&self, id: FragmentId) -> Result<Option<Fragment>, RepoError> {
        let row = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select
                        id,
                        project_id,
                        kind,
                        provenance::text as "provenance!",
                        audio_uri,
                        duration_ms,
                        sample_rate,
                        note_text,
                        state::text as "state!",
                        parent_fragment_id,
                        created_at_ms
                    from fragments
                    where id = $1
                    "#,
                    id.0,
                )
                .fetch_optional(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        match row {
            None => Ok(None),
            Some(r) => Ok(Some(Self::row_to_fragment(
                r.id,
                r.project_id,
                r.kind,
                r.provenance,
                r.audio_uri,
                r.duration_ms,
                r.sample_rate,
                r.note_text,
                r.state,
                r.parent_fragment_id,
                r.created_at_ms,
            )?)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::fragment::FragmentKind;

    // Live-DB round-trip. Ignored by default; run against a migrated Postgres with:
    //   DATABASE_URL=postgres://... cargo test -p nameless-adapters --features postgres -- --ignored
    #[test]
    #[ignore = "requires a live Postgres (DATABASE_URL) + applied migrations"]
    fn round_trip_project_and_fragment() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL for the ignored DB test");
        let repo = PostgresFragmentRepo::connect(&url).unwrap();

        let project = Project::new("pg round-trip".into());
        repo.insert_project(&project).unwrap();

        let frag = Fragment::new_capture(
            project.id,
            FragmentKind::Hook,
            "deadbeefcafe".into(),
            Some(2000),
            Some(48_000),
            "chorus hook".into(),
        );
        repo.insert_fragment(&frag).unwrap();

        let got = repo.get_fragment(frag.id).unwrap().unwrap();
        assert_eq!(got, frag);

        let listed = repo.list_fragments(Some(project.id)).unwrap();
        assert!(listed.iter().any(|f| f.id == frag.id));
    }
}
