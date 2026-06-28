//! Production reference store on Postgres (sqlx) — behind the `postgres` feature.
//!
//! Mirrors `PostgresFragmentRepo` exactly: compile-time-checked `query!` SQL, a sync trait over the
//! async driver via an owned Tokio runtime + `block_on`, and enum mapping through canonical
//! snake_case labels (`$n::text::reference_role`). See `repo_pg.rs` for the rationale on all three.
//!
//! ## Two writers, one row — the deliberate split (mirrors Phase 2)
//!
//! The Rust control plane writes `reference_tracks` (on upload) and `project_reference_context` (on
//! attach). It does NOT write `reference_context`: the embedding + non-melodic targets + vibe are
//! produced and persisted by the Python `RestrictedReferenceAnalyzer` (exactly as `fragment_features`
//! is written by the Python feature worker, not Rust). This adapter only READS that row, and only as
//! a COMPACT summary: it projects `vector_dims(clap_style_embedding)` — an integer — never the
//! embedding vector itself, so the large array never crosses into the control plane or agent context
//! (the compact-output contract). `tonal_balance` (jsonb) is read as text and parsed, avoiding a
//! sqlx `json` feature dependency.

use std::sync::Arc;

use sqlx::postgres::{PgPool, PgPoolOptions};
use tokio::runtime::Runtime;

use nameless_core::error::RepoError;
use nameless_core::fragment::ProjectId;
use nameless_core::ports::ReferenceStore;
use nameless_core::reference::{
    ProjectReference, ReferenceContextSummary, ReferenceRole, ReferenceTrack, ReferenceTrackId,
    TonalBalance,
};

/// A [`ReferenceStore`] backed by Postgres.
pub struct PostgresReferenceStore {
    rt: Arc<Runtime>,
    pool: PgPool,
}

impl PostgresReferenceStore {
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
    /// runtime across the fragment repo, queue, store, and this reference store).
    pub fn new(rt: Arc<Runtime>, pool: PgPool) -> Self {
        Self { rt, pool }
    }
}

impl ReferenceStore for PostgresReferenceStore {
    fn insert_track(&self, track: &ReferenceTrack) -> Result<(), RepoError> {
        let duration = track.duration_ms.map(|v| v as i32);
        let sample_rate = track.sample_rate.map(|v| v as i32);
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    insert into reference_tracks
                        (id, audio_uri, title, artist, duration_ms, sample_rate, uploaded_at_ms)
                    values ($1, $2, $3, $4, $5, $6, $7)
                    "#,
                    track.id.0,
                    track.audio_uri,
                    track.title,
                    track.artist,
                    duration,
                    sample_rate,
                    track.uploaded_at_ms,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn get_track(&self, id: ReferenceTrackId) -> Result<Option<ReferenceTrack>, RepoError> {
        let row = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select id, audio_uri, title, artist, duration_ms, sample_rate, uploaded_at_ms
                    from reference_tracks
                    where id = $1
                    "#,
                    id.0,
                )
                .fetch_optional(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        Ok(row.map(|r| ReferenceTrack {
            id: ReferenceTrackId(r.id),
            audio_uri: r.audio_uri,
            title: r.title,
            artist: r.artist,
            duration_ms: r.duration_ms.map(|v| v as u32),
            sample_rate: r.sample_rate.map(|v| v as u32),
            uploaded_at_ms: r.uploaded_at_ms,
        }))
    }

    fn list_tracks(&self) -> Result<Vec<ReferenceTrack>, RepoError> {
        let rows = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select id, audio_uri, title, artist, duration_ms, sample_rate, uploaded_at_ms
                    from reference_tracks
                    order by uploaded_at_ms desc
                    "#,
                )
                .fetch_all(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        Ok(rows
            .into_iter()
            .map(|r| ReferenceTrack {
                id: ReferenceTrackId(r.id),
                audio_uri: r.audio_uri,
                title: r.title,
                artist: r.artist,
                duration_ms: r.duration_ms.map(|v| v as u32),
                sample_rate: r.sample_rate.map(|v| v as u32),
                uploaded_at_ms: r.uploaded_at_ms,
            })
            .collect())
    }

    fn get_context_summary(
        &self,
        id: ReferenceTrackId,
    ) -> Result<Option<ReferenceContextSummary>, RepoError> {
        // CRITICAL: we project `vector_dims(...)` (an int), NOT `clap_style_embedding` — the
        // embedding vector is never read into the control plane. `tonal_balance` is read as text and
        // parsed below. NO melodic column exists to select (the schema has none).
        let row = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select
                        reference_track_id,
                        genre,
                        tempo_bpm_min,
                        tempo_bpm_max,
                        lufs,
                        tonal_balance::text as "tonal_balance!",
                        stereo_width,
                        vibe_description,
                        coalesce(vector_dims(clap_style_embedding), 0) as "embedding_dim!",
                        analyzer_version
                    from reference_context
                    where reference_track_id = $1
                    "#,
                    id.0,
                )
                .fetch_optional(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        match row {
            None => Ok(None),
            Some(r) => {
                let tonal_balance: TonalBalance = serde_json::from_str(&r.tonal_balance)
                    .map_err(|e| RepoError::Serialization(format!("tonal_balance: {e}")))?;
                Ok(Some(ReferenceContextSummary {
                    reference_track_id: ReferenceTrackId(r.reference_track_id),
                    genre: r.genre,
                    tempo_bpm_min: r.tempo_bpm_min,
                    tempo_bpm_max: r.tempo_bpm_max,
                    lufs: r.lufs,
                    tonal_balance,
                    stereo_width: r.stereo_width,
                    vibe_description: r.vibe_description,
                    embedding_dim: r.embedding_dim as usize,
                    analyzer_version: r.analyzer_version,
                }))
            }
        }
    }

    fn attach(
        &self,
        project: ProjectId,
        reference: ReferenceTrackId,
        role: ReferenceRole,
    ) -> Result<(), RepoError> {
        let role_label = role.as_str();
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    insert into project_reference_context (project_id, reference_track_id, role)
                    values ($1, $2, $3::text::reference_role)
                    on conflict (project_id, reference_track_id)
                    do update set role = excluded.role
                    "#,
                    project.0,
                    reference.0,
                    role_label,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn list_project_references(
        &self,
        project: ProjectId,
    ) -> Result<Vec<ProjectReference>, RepoError> {
        let rows = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select reference_track_id, role::text as "role!"
                    from project_reference_context
                    where project_id = $1
                    "#,
                    project.0,
                )
                .fetch_all(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        rows.into_iter()
            .map(|r| {
                let role = ReferenceRole::from_db_str(&r.role)
                    .ok_or_else(|| RepoError::Serialization(format!("unknown role: {}", r.role)))?;
                Ok(ProjectReference {
                    reference_track_id: ReferenceTrackId(r.reference_track_id),
                    role,
                })
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Live-DB round-trip. Ignored by default; run against a migrated Postgres with:
    //   DATABASE_URL=postgres://... cargo test -p nameless-adapters --features postgres -- --ignored
    #[test]
    #[ignore = "requires a live Postgres (DATABASE_URL) + applied migrations 0001..0003"]
    fn round_trip_track_and_link() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL for the ignored DB test");
        let store = PostgresReferenceStore::connect(&url).unwrap();

        let track = ReferenceTrack::new_upload(
            "deadbeefcafe".into(),
            Some("Trust".into()),
            Some("Brent Faiyaz".into()),
            Some(210_000),
            Some(44_100),
        );
        store.insert_track(&track).unwrap();
        let got = store.get_track(track.id).unwrap().unwrap();
        assert_eq!(got.audio_uri, track.audio_uri);

        let project = ProjectId::new();
        // (project must exist in `projects` for the FK; the test harness seeds it separately.)
        store
            .attach(project, track.id, ReferenceRole::Vibe)
            .unwrap();
        let links = store.list_project_references(project).unwrap();
        assert!(links.iter().any(|l| l.reference_track_id == track.id));
    }
}
