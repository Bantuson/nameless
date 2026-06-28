//! Durable, Postgres-backed job queue (sqlxmq) — behind the `postgres` feature.
//!
//! STACK §5 decision: at solo scale the queue is Postgres-backed (sqlxmq), NOT NATS/Redis — it
//! reuses the same `PgPool` and gives at-least-once delivery, durability across restart, retries,
//! and backpressure with zero extra infrastructure. The trait stays the same as the in-memory
//! fake, so the swap is invisible to callers.
//!
//! ## Phase 1 enqueues only — and the consume/ack/retry methods fail LOUD (WR-02)
//!
//! sqlxmq's model is a registered `JobRegistry` + a spawned `JobRunner` that pulls messages and
//! dispatches them to handlers. Phase 1 deliberately runs NO consumer — the feature worker that
//! consumes `FeatureExtract` is Phase 2. So this adapter fully implements the durable **enqueue**
//! side (the only thing capture needs). The `consume`/`mark_done`/`mark_retry` methods are owned by
//! the Phase-2 `JobRunner`; rather than silently returning success-shaped values (`Ok(None)` /
//! `Ok(())` / `Ok(Failed)`) that would diverge from the `JobQueue` contract and the in-memory fake,
//! they return an explicit `JobError::Backend` so a mistaken caller fails immediately instead of
//! trusting a lie. `capacity()` reports `usize::MAX` (durable queue = effectively unbounded at
//! enqueue), not a fabricated bound. The durability of enqueue is proven by the ignored cross-restart
//! test below.
//!
//! ## Per-kind routing (WR-03)
//!
//! Each `JobEnvelope` kind is registered as its OWN sqlxmq job + channel (`features`, `separate`,
//! `separate_track`, `reference`) and `enqueue` selects the builder by matching on the envelope. The
//! queue's own dispatch then routes a stored message to the correct worker plane — the Demucs/
//! reference kinds target the Python plane and stay on distinct channels so it can filter without
//! the feature handler ever seeing them.
//!
//! Retries/backoff: when the Phase-2 runner is wired, sqlxmq's per-job `set_retries` +
//! `set_retry_backoff` are configured to mirror [`RetryPolicy`] (≈5 attempts, exponential).

use std::sync::Arc;

use sqlx::postgres::{PgPool, PgPoolOptions};
use sqlxmq::CurrentJob;
use tokio::runtime::Runtime;

use nameless_core::job::{
    JobEnvelope, JobError, JobId, JobQueue, JobRecord, JobStatus, RetryPolicy,
};

// One registered sqlxmq job (name + channel) PER `JobEnvelope` kind. This is what lets the queue's
// own dispatch route a stored message to the right worker plane (WR-03) instead of delivering every
// kind to a single handler that must then re-inspect the JSON `job` tag. Distinct channels also let
// each kind carry its own concurrency/retry policy later, and let the Python worker plane filter by
// channel when it consumes `mq_msgs` directly (the Demucs/reference kinds are Python-plane work, not
// Rust handlers). Phase 1 starts NO runner, so every body here is an ack-only placeholder that the
// owning phase (2 = features, 8 = separation, 7 = reference) replaces with the real worker.

/// `FeatureExtract` → the Phase-2 feature worker (Rust or Python). Channel `features`.
#[sqlxmq::job(channel_name = "features")]
pub async fn feature_extract_job(
    mut current: CurrentJob,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Phase 2: deserialize current.json::<JobEnvelope>()? and run the worker. For now, ack so a
    // stray runner (if ever started) does not loop.
    current.complete().await?;
    Ok(())
}

/// `Separate` (a fragment into stems) → the Phase-8 sampling/separation worker. Channel `separate`.
#[sqlxmq::job(channel_name = "separate")]
pub async fn separate_fragment_job(
    mut current: CurrentJob,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    current.complete().await?;
    Ok(())
}

/// `SeparateTrack` (a reference track into its retained stem library, SAMP-01) → the Python Demucs
/// worker plane. Channel `separate_track` keeps it off the feature/fragment channels so the Python
/// side can filter without cross-talk.
#[sqlxmq::job(channel_name = "separate_track")]
pub async fn separate_track_job(
    mut current: CurrentJob,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    current.complete().await?;
    Ok(())
}

/// `AnalyzeReference` (non-melodic vibe/target extraction) → the Phase-7 Python reference analyzer.
/// Channel `reference`.
#[sqlxmq::job(channel_name = "reference")]
pub async fn analyze_reference_job(
    mut current: CurrentJob,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    current.complete().await?;
    Ok(())
}

/// A [`JobQueue`] backed by sqlxmq over Postgres.
pub struct SqlxmqJobQueue {
    rt: Arc<Runtime>,
    pool: PgPool,
    policy: RetryPolicy,
}

impl SqlxmqJobQueue {
    /// Connect using a fresh owned runtime + pool. Convenience for the CLI server profile.
    pub fn connect(database_url: &str) -> Result<Self, JobError> {
        let rt = Arc::new(Runtime::new().map_err(|e| JobError::Backend { msg: e.to_string() })?);
        let pool = rt
            .block_on(async {
                PgPoolOptions::new()
                    .max_connections(5)
                    .connect(database_url)
                    .await
            })
            .map_err(|e| JobError::Backend { msg: e.to_string() })?;
        Ok(Self {
            rt,
            pool,
            policy: RetryPolicy::default(),
        })
    }

    /// Construct from a shared runtime + pool (share one runtime across repo/queue/store).
    pub fn new(rt: Arc<Runtime>, pool: PgPool) -> Self {
        Self {
            rt,
            pool,
            policy: RetryPolicy::default(),
        }
    }
}

impl JobQueue for SqlxmqJobQueue {
    /// Durably enqueue a job: serialize the envelope to JSON and spawn it onto sqlxmq's table under
    /// the sqlxmq job/channel that matches the envelope KIND (WR-03), so the queue itself routes the
    /// message to the correct worker plane. The row survives a process restart (proven by the
    /// ignored test).
    fn enqueue(&self, env: JobEnvelope) -> Result<JobId, JobError> {
        let payload =
            serde_json::to_value(&env).map_err(|e| JobError::Serialization(e.to_string()))?;
        let backoff = self.policy.backoff(0);
        // Mirror the RetryPolicy onto sqlxmq's own retry machinery.
        let retries = self.policy.max_attempts.saturating_sub(1) as usize;

        // Select the per-kind builder (distinct job name + channel). The builder type is the same
        // (`sqlxmq::JobBuilder`) across all registrations — only the embedded name/channel differ —
        // so the arms unify and the spawn logic stays in one place.
        let mut builder = match &env {
            JobEnvelope::FeatureExtract { .. } => feature_extract_job.builder(),
            JobEnvelope::Separate { .. } => separate_fragment_job.builder(),
            JobEnvelope::SeparateTrack { .. } => separate_track_job.builder(),
            JobEnvelope::AnalyzeReference { .. } => analyze_reference_job.builder(),
        };

        let uuid = self.rt.block_on(async {
            builder
                .set_json(&payload)
                .map_err(|e| JobError::Serialization(e.to_string()))?
                .set_retries(retries)
                .set_retry_backoff(backoff)
                .spawn(&self.pool)
                .await
                .map_err(|e| JobError::Backend { msg: e.to_string() })
        })?;

        Ok(JobId(uuid))
    }

    /// **Not implemented in the enqueue-only Phase-1 adapter.** Consumption is owned by the Phase-2
    /// sqlxmq `JobRunner` (which dispatches to the registered handlers), NOT by manual polling.
    /// Returning a loud `Err` rather than `Ok(None)` (WR-02) means a mistaken Phase-1 caller fails
    /// immediately instead of silently believing the queue was empty — the in-memory fake's FIFO
    /// claim contract is deliberately NOT faked here.
    fn consume(&self) -> Result<Option<JobRecord>, JobError> {
        Err(JobError::Backend {
            msg: "SqlxmqJobQueue::consume is owned by the Phase-2 sqlxmq JobRunner; \
                  this enqueue-only adapter does not poll for jobs"
                .into(),
        })
    }

    /// **Not implemented here.** Acking happens inside the runner's job handler
    /// (`CurrentJob::complete`) in Phase 2. Fails loud rather than pretending success (WR-02).
    fn mark_done(&self, _id: JobId) -> Result<(), JobError> {
        Err(JobError::Backend {
            msg: "SqlxmqJobQueue::mark_done is handled by the runner's CurrentJob::complete \
                  in Phase 2; not available on the enqueue-only adapter"
                .into(),
        })
    }

    /// **Not implemented here.** Retry/dead-letter is driven by sqlxmq's per-job retry config (set at
    /// enqueue) and the runner. Returning `Err` rather than a fake `Ok(JobStatus::Failed)` (WR-02)
    /// keeps the attempt-counting/dead-letter contract honest: this adapter does not increment
    /// attempts or dead-letter, so it must not claim to.
    fn mark_retry(&self, _id: JobId) -> Result<JobStatus, JobError> {
        Err(JobError::Backend {
            msg: "SqlxmqJobQueue::mark_retry is driven by sqlxmq's per-job retry machinery in \
                  Phase 2; the enqueue-only adapter does not manage attempts"
                .into(),
        })
    }

    /// The durable Postgres-backed queue applies no fixed in-process depth bound at enqueue time
    /// (enqueue never returns `JobError::Full`), so the honest capacity is "effectively unbounded".
    /// Reporting `usize::MAX` (WR-02) rather than a fabricated `256` avoids implying a backpressure
    /// cap the adapter does not enforce; real backpressure, when wired, is the Phase-2 runner's
    /// concurrency limit, not a queue-depth ceiling.
    fn capacity(&self) -> usize {
        usize::MAX
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::fragment::FragmentId;

    // Durability across a "restart": enqueue, drop the pool, reconnect, assert the message row is
    // still present in sqlxmq's table. Ignored by default; run with:
    //   DATABASE_URL=postgres://... cargo test -p nameless-adapters --features postgres -- --ignored
    #[test]
    #[ignore = "requires a live Postgres (DATABASE_URL) + sqlxmq migrations applied"]
    fn enqueue_survives_pool_drop() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL for the ignored queue test");

        let queue = SqlxmqJobQueue::connect(&url).unwrap();
        let id = queue
            .enqueue(JobEnvelope::FeatureExtract {
                fragment_id: FragmentId::new(),
            })
            .unwrap();

        // Drop the queue (and its pool + runtime) to model a process exit.
        drop(queue);

        // Reconnect with a brand-new pool and confirm the durable row persists.
        let rt = Runtime::new().unwrap();
        let pool = rt
            .block_on(PgPoolOptions::new().max_connections(1).connect(&url))
            .unwrap();
        let count: i64 = rt
            .block_on(async {
                sqlx::query_scalar!(r#"select count(*) as "count!" from mq_msgs where id = $1"#, id.0)
                    .fetch_one(&pool)
                    .await
            })
            .unwrap();
        assert_eq!(count, 1, "enqueued job must survive a pool drop");
    }
}
