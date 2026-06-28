//! Production stem + attribution store on Postgres (sqlx) — behind the `postgres` feature.
//!
//! Mirrors `PostgresReferenceStore` exactly: compile-time-checked `query!` SQL, a sync trait over the
//! async driver via an owned Tokio runtime + `block_on`, and enum mapping through canonical
//! snake_case labels (`$n::text::rights_status`, `stem_type` as plain `text`). One object satisfies
//! BOTH [`StemStore`] and [`AttributionStore`] (hence [`nameless_core::ports::SampleStore`]),
//! because both back onto the same database.
//!
//! ## The completeness invariant, at the DB edge
//!
//! `sample_attribution` columns are all `NOT NULL` (migration 0004) — the DB mirror of the Rust
//! `CompleteAttribution` type. This adapter only ever WRITES a [`SampleAttribution`], which is built
//! from a `CompleteAttribution`, so a partial row can never be inserted; and on READ it reconstructs a
//! `CompleteAttribution` via `CompleteAttribution::new(...)` from the `NOT NULL` columns, so a row
//! that exists is always complete. The two completeness guarantees (type + schema) reinforce.

use std::sync::Arc;

use sqlx::postgres::{PgPool, PgPoolOptions};
use tokio::runtime::Runtime;

use nameless_core::attribution::{CompleteAttribution, RightsStatus, SampleAttribution};
use nameless_core::error::RepoError;
use nameless_core::fragment::{FragmentId, ProjectId};
use nameless_core::ports::{AttributionStore, StemStore};
use nameless_core::reference::ReferenceTrackId;
use nameless_core::stems::{Stem, StemId, StemType};

/// A [`StemStore`] + [`AttributionStore`] backed by Postgres.
pub struct PostgresSampleStore {
    rt: Arc<Runtime>,
    pool: PgPool,
}

impl PostgresSampleStore {
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

    /// Construct from a shared runtime + pool (lets the server profile share one runtime across all
    /// the Postgres adapters).
    pub fn new(rt: Arc<Runtime>, pool: PgPool) -> Self {
        Self { rt, pool }
    }
}

impl StemStore for PostgresSampleStore {
    fn insert_stem(&self, stem: &Stem) -> Result<(), RepoError> {
        // Bind as i64 → the `bigint` columns hold the full u32 domain without narrowing (an `as i32`
        // would wrap negative for values > i32::MAX, diverging from the file/in-memory stores).
        let duration = stem.duration_ms.map(|v| v as i64);
        let sample_rate = stem.sample_rate.map(|v| v as i64);
        let stem_type = stem.stem_type.as_str();
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    insert into stems
                        (id, reference_track_id, stem_type, audio_uri, separator_model,
                         separator_version, duration_ms, sample_rate, created_at_ms)
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    on conflict (reference_track_id, audio_uri) do nothing
                    "#,
                    stem.id.0,
                    stem.reference_track_id.0,
                    stem_type,
                    stem.audio_uri,
                    stem.separator_model,
                    stem.separator_version,
                    duration,
                    sample_rate,
                    stem.created_at_ms,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn get_stem(&self, id: StemId) -> Result<Option<Stem>, RepoError> {
        let row = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select id, reference_track_id, stem_type, audio_uri, separator_model,
                           separator_version, duration_ms, sample_rate, created_at_ms
                    from stems where id = $1
                    "#,
                    id.0,
                )
                .fetch_optional(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        match row {
            None => Ok(None),
            Some(r) => Ok(Some(Stem {
                id: StemId(r.id),
                reference_track_id: ReferenceTrackId(r.reference_track_id),
                stem_type: parse_stem_type(&r.stem_type)?,
                audio_uri: r.audio_uri,
                separator_model: r.separator_model,
                separator_version: r.separator_version,
                duration_ms: r.duration_ms.map(|v| v as u32),
                sample_rate: r.sample_rate.map(|v| v as u32),
                created_at_ms: r.created_at_ms,
            })),
        }
    }

    fn list_stems(&self, track: ReferenceTrackId) -> Result<Vec<Stem>, RepoError> {
        let rows = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select id, reference_track_id, stem_type, audio_uri, separator_model,
                           separator_version, duration_ms, sample_rate, created_at_ms
                    from stems
                    where reference_track_id = $1
                    order by created_at_ms desc
                    "#,
                    track.0,
                )
                .fetch_all(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        rows.into_iter()
            .map(|r| {
                Ok(Stem {
                    id: StemId(r.id),
                    reference_track_id: ReferenceTrackId(r.reference_track_id),
                    stem_type: parse_stem_type(&r.stem_type)?,
                    audio_uri: r.audio_uri,
                    separator_model: r.separator_model,
                    separator_version: r.separator_version,
                    duration_ms: r.duration_ms.map(|v| v as u32),
                    sample_rate: r.sample_rate.map(|v| v as u32),
                    created_at_ms: r.created_at_ms,
                })
            })
            .collect()
    }
}

impl AttributionStore for PostgresSampleStore {
    fn insert_attribution(&self, attribution: &SampleAttribution) -> Result<(), RepoError> {
        let a = &attribution.attribution;
        let stem_type = a.stem_type.as_str();
        let rights = a.rights_status.as_str();
        // i64 → `bigint` columns: the full u32 ms range round-trips without i32 wrap (matches --local).
        let start = a.start_ms as i64;
        let end = a.end_ms as i64;
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    insert into sample_attribution
                        (fragment_id, project_id, reference_track_id, stem_id, source_title,
                         source_artist, stem_type, start_ms, end_ms, rights_status, created_at_ms)
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::text::rights_status, $11)
                    on conflict (fragment_id) do nothing
                    "#,
                    attribution.fragment_id.0,
                    attribution.project_id.0,
                    a.source_track_id.0,
                    a.stem_id.0,
                    a.source_title,
                    a.source_artist,
                    stem_type,
                    start,
                    end,
                    rights,
                    attribution.created_at_ms,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }

    fn get_attribution(
        &self,
        fragment: FragmentId,
    ) -> Result<Option<SampleAttribution>, RepoError> {
        let row = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select fragment_id, project_id, reference_track_id, stem_id, source_title,
                           source_artist, stem_type, start_ms, end_ms,
                           rights_status::text as "rights_status!", created_at_ms
                    from sample_attribution where fragment_id = $1
                    "#,
                    fragment.0,
                )
                .fetch_optional(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        match row {
            None => Ok(None),
            Some(r) => Ok(Some(hydrate_attribution(
                FragmentId(r.fragment_id),
                ProjectId(r.project_id),
                ReferenceTrackId(r.reference_track_id),
                StemId(r.stem_id),
                r.source_title,
                r.source_artist,
                &r.stem_type,
                r.start_ms,
                r.end_ms,
                &r.rights_status,
                r.created_at_ms,
            )?)),
        }
    }

    fn list_project_attributions(
        &self,
        project: ProjectId,
    ) -> Result<Vec<SampleAttribution>, RepoError> {
        let rows = self
            .rt
            .block_on(async {
                sqlx::query!(
                    r#"
                    select fragment_id, project_id, reference_track_id, stem_id, source_title,
                           source_artist, stem_type, start_ms, end_ms,
                           rights_status::text as "rights_status!", created_at_ms
                    from sample_attribution where project_id = $1
                    order by created_at_ms
                    "#,
                    project.0,
                )
                .fetch_all(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;

        rows.into_iter()
            .map(|r| {
                hydrate_attribution(
                    FragmentId(r.fragment_id),
                    ProjectId(r.project_id),
                    ReferenceTrackId(r.reference_track_id),
                    StemId(r.stem_id),
                    r.source_title,
                    r.source_artist,
                    &r.stem_type,
                    r.start_ms,
                    r.end_ms,
                    &r.rights_status,
                    r.created_at_ms,
                )
            })
            .collect()
    }

    fn delete_attribution(&self, fragment: FragmentId) -> Result<(), RepoError> {
        // Idempotent: a delete affecting zero rows is still Ok. (On the Postgres profile a
        // `delete_fragment` would also remove this via the FK cascade; this explicit delete keeps
        // the compensating cleanup correct on every profile and order-independent.)
        self.rt
            .block_on(async {
                sqlx::query!(
                    r#"delete from sample_attribution where fragment_id = $1"#,
                    fragment.0,
                )
                .execute(&self.pool)
                .await
            })
            .map_err(|e| RepoError::Backend(e.to_string()))?;
        Ok(())
    }
}

fn parse_stem_type(s: &str) -> Result<StemType, RepoError> {
    StemType::from_db_str(s).ok_or_else(|| RepoError::Serialization(format!("unknown stem_type: {s}")))
}

/// Rebuild a complete `SampleAttribution` from `NOT NULL` columns. Because `CompleteAttribution::new`
/// takes every field non-optionally and the columns are `NOT NULL`, the result is always complete.
#[allow(clippy::too_many_arguments)]
fn hydrate_attribution(
    fragment_id: FragmentId,
    project_id: ProjectId,
    source_track_id: ReferenceTrackId,
    stem_id: StemId,
    source_title: String,
    source_artist: String,
    stem_type: &str,
    start_ms: i64,
    end_ms: i64,
    rights_status: &str,
    created_at_ms: i64,
) -> Result<SampleAttribution, RepoError> {
    let stem_type = parse_stem_type(stem_type)?;
    let rights = RightsStatus::from_db_str(rights_status)
        .ok_or_else(|| RepoError::Serialization(format!("unknown rights_status: {rights_status}")))?;
    let attribution = CompleteAttribution::new(
        source_track_id,
        stem_id,
        source_title,
        source_artist,
        stem_type,
        start_ms as u32,
        end_ms as u32,
        rights,
    );
    Ok(SampleAttribution {
        fragment_id,
        project_id,
        attribution,
        created_at_ms,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::attribution::PartialAttribution;

    // Live-DB round-trip. Ignored by default; run against a migrated Postgres with:
    //   DATABASE_URL=postgres://... cargo test -p nameless-adapters --features postgres -- --ignored
    #[test]
    #[ignore = "requires a live Postgres (DATABASE_URL) + applied migrations 0001..0004"]
    fn round_trip_stem_and_attribution() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL for the ignored DB test");
        let store = PostgresSampleStore::connect(&url).unwrap();

        let track = ReferenceTrackId::new();
        let stem = Stem::new(
            track,
            StemType::Vocals,
            "stemhash".into(),
            "htdemucs_ft".into(),
            "4.0.1".into(),
            Some(210_000),
            Some(44_100),
        );
        // (track + project + fragment rows must exist for the FKs; the harness seeds them.)
        store.insert_stem(&stem).unwrap();
        let got = store.get_stem(stem.id).unwrap().unwrap();
        assert_eq!(got.audio_uri, "stemhash");

        let project = ProjectId::new();
        let frag = FragmentId::new();
        let attr = SampleAttribution::new(
            frag,
            project,
            PartialAttribution {
                source_track_id: Some(track),
                stem_id: Some(stem.id),
                source_title: Some("Trust".into()),
                source_artist: Some("Brent Faiyaz".into()),
                stem_type: Some(StemType::Vocals),
                start_ms: Some(12_000),
                end_ms: Some(18_000),
                rights_status: Some(RightsStatus::CopyrightedUncleared),
            }
            .into_complete()
            .unwrap(),
        );
        store.insert_attribution(&attr).unwrap();
        let back = store.get_attribution(frag).unwrap().unwrap();
        assert_eq!(back, attr);
    }
}
