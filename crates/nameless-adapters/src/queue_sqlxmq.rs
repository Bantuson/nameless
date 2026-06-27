//! Durable, Postgres-backed job queue (sqlxmq) — behind the `postgres` feature.
//!
//! STACK §5 decision: at solo scale the queue is Postgres-backed (sqlxmq), NOT NATS/Redis — it
//! reuses the same `PgPool` and gives at-least-once delivery, durability across restart, retries,
//! and backpressure with zero extra infrastructure. The trait stays the same as the in-memory
//! fake, so the swap is invisible to callers.
//!
//! ## Phase 1 enqueues only
//!
//! sqlxmq's model is a registered `JobRegistry` + a spawned `JobRunner` that pulls messages and
//! dispatches them to handlers. Phase 1 deliberately runs NO consumer — the feature worker that
//! consumes `FeatureExtract` is Phase 2. So this adapter fully implements the durable **enqueue**
//! side (the only thing capture needs), while `consume`/`mark_done`/`mark_retry` are owned by the
//! Phase-2 `JobRunner` and are intentionally inert here (documented per method). The durability of
//! enqueue is proven by the ignored cross-restart test below.
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

/// The Phase-2 feature-extraction job handler.
///
/// Registered so sqlxmq knows the job name for enqueue; its body is a no-op in Phase 1 because no
/// runner is started. Phase 2 replaces the body with the real worker (read the `JobEnvelope` JSON,
/// run feature extraction, drive `Captured → Analyzed`).
#[sqlxmq::job(channel_name = "features")]
pub async fn feature_extract_job(
    mut current: CurrentJob,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Phase 2: deserialize current.json::<JobEnvelope>()? and run the worker. For now, ack so a
    // stray runner (if ever started) does not loop.
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
    /// Durably enqueue a job: serialize the envelope to JSON and spawn it onto sqlxmq's table.
    /// The row survives a process restart (proven by the ignored test).
    fn enqueue(&self, env: JobEnvelope) -> Result<JobId, JobError> {
        let payload =
            serde_json::to_value(&env).map_err(|e| JobError::Serialization(e.to_string()))?;
        let backoff = self.policy.backoff(0);

        let uuid = self
            .rt
            .block_on(async {
                feature_extract_job
                    .builder()
                    .set_json(&payload)
                    .map_err(|e| JobError::Serialization(e.to_string()))?
                    // Mirror the RetryPolicy onto sqlxmq's own retry machinery.
                    .set_retries(self.policy.max_attempts.saturating_sub(1) as usize)
                    .set_retry_backoff(backoff)
                    .spawn(&self.pool)
                    .await
                    .map_err(|e| JobError::Backend { msg: e.to_string() })
            })?;

        Ok(JobId(uuid))
    }

    /// Consumption is owned by the Phase-2 sqlxmq `JobRunner`, not manual polling. Phase 1 runs no
    /// consumer, so this is intentionally a no-op (returns `None`). See the module docs.
    fn consume(&self) -> Result<Option<JobRecord>, JobError> {
        Ok(None)
    }

    /// Acking is handled inside the runner's job handler (`CurrentJob::complete`) in Phase 2; there
    /// is nothing for an external caller to ack in Phase 1.
    fn mark_done(&self, _id: JobId) -> Result<(), JobError> {
        Ok(())
    }

    /// Retry/dead-letter is managed by sqlxmq's per-job retry config (set at enqueue) and the
    /// runner; an external `mark_retry` is a no-op in the enqueue-only Phase-1 adapter.
    fn mark_retry(&self, _id: JobId) -> Result<JobStatus, JobError> {
        Ok(JobStatus::Failed)
    }

    /// sqlxmq applies backpressure via the runner's concurrency limit (Phase 2). The reported
    /// capacity mirrors that intended bound.
    fn capacity(&self) -> usize {
        // Concurrency bound the Phase-2 runner will enforce; surfaced for parity with the fake.
        256
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
