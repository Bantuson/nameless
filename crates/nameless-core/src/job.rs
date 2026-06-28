//! The durable job-queue contract (CAP-07).
//!
//! When a fragment is captured, downstream work (feature extraction, stem separation) must be
//! enqueued for the worker plane. At solo scale this is a **Postgres-backed queue (sqlxmq)**, not
//! NATS/Redis (STACK §5) — but that decision is hidden behind the [`JobQueue`] trait so the
//! in-memory fake and the production sqlxmq impl are interchangeable.
//!
//! Phase 1 **enqueues only**: there is no running consumer (the feature worker is Phase 2). The
//! in-memory adapter exercises the retry / backpressure / dead-letter semantics in RAM-safe tests
//! so the contract is proven before the heavy leaf exists.
//!
//! The envelope is a typed enum serialized to self-describing JSON, so the same payload survives
//! the trip through the sqlxmq message column and back without a stringly-typed schema.

use std::time::Duration;

use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

use crate::fragment::FragmentId;
use crate::reference::ReferenceTrackId;

/// A typed unit of work crossing the control-plane → worker-plane seam.
///
/// Internally tagged (`{"job": "feature_extract", "fragment_id": "…"}`) so the JSON is
/// self-describing in the queue's payload column. Only the two Phase-1/2 job kinds exist now;
/// real handlers arrive in Phase 2.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "job", rename_all = "snake_case")]
pub enum JobEnvelope {
    /// Compute f0/chroma/onsets/key/LUFS + embeddings for a captured fragment (Phase 2 worker).
    FeatureExtract { fragment_id: FragmentId },
    /// Separate a track/fragment into stems (Phase 8 sampling worker).
    Separate { fragment_id: FragmentId },
    /// Extract NON-melodic reference context (CLAP style embedding + vibe + sonic targets) for an
    /// uploaded reference track (Phase 7 worker). Enqueued by `reference upload`; handled by the
    /// Python `RestrictedReferenceAnalyzer`, which never computes f0/chroma (the non-cloning path).
    AnalyzeReference { reference_track_id: ReferenceTrackId },
}

/// Strongly-typed job identifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct JobId(pub Uuid);

impl JobId {
    pub fn new() -> Self {
        JobId(Uuid::new_v4())
    }
}

impl Default for JobId {
    fn default() -> Self {
        Self::new()
    }
}

impl std::fmt::Display for JobId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Lifecycle of a queued job.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JobStatus {
    /// Waiting to be consumed.
    Queued,
    /// Claimed by a consumer, not yet acked.
    InProgress,
    /// Failed an attempt; eligible for retry until `max_attempts`.
    Failed,
    /// Exhausted `max_attempts` — parked, never redelivered.
    DeadLettered,
    /// Acked successfully.
    Done,
}

/// A queued job plus its delivery bookkeeping.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct JobRecord {
    pub id: JobId,
    pub envelope: JobEnvelope,
    /// Number of delivery attempts so far.
    pub attempts: u32,
    pub status: JobStatus,
}

/// Retry/backoff policy. Bounds retries so a poison job cannot loop forever (DoS mitigation).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RetryPolicy {
    /// Maximum delivery attempts before dead-lettering.
    pub max_attempts: u32,
    /// Base backoff; the effective backoff grows exponentially per attempt (capped).
    pub base_backoff_ms: u64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        // ~5 attempts, exponential backoff from 500ms (CONTEXT Job Queue defaults).
        RetryPolicy {
            max_attempts: 5,
            base_backoff_ms: 500,
        }
    }
}

impl RetryPolicy {
    /// Exponential backoff for a given (zero-based) attempt, capped at 60s to stay monotonic and
    /// bounded. `attempt 0` → base, `attempt n` → base * 2^n (saturating).
    pub fn backoff(&self, attempt: u32) -> Duration {
        const CAP_MS: u64 = 60_000;
        let factor = 2u64.saturating_pow(attempt);
        let ms = self.base_backoff_ms.saturating_mul(factor).min(CAP_MS);
        Duration::from_millis(ms)
    }
}

/// Failure modes of a [`JobQueue`].
#[derive(Debug, Error)]
pub enum JobError {
    /// The queue is at capacity — backpressure. The caller should slow down / retry later.
    #[error("job queue is full (at capacity)")]
    Full,
    /// No job exists for the given id.
    #[error("job not found: {0}")]
    NotFound(JobId),
    /// (De)serialization of the envelope failed.
    #[error("job serialization error: {0}")]
    Serialization(String),
    /// The backend rejected or failed the operation.
    #[error("job queue backend error: {msg}")]
    Backend { msg: String },
}

/// A durable work queue. Implementors: `InMemoryJobQueue` (tests/`--local`), `SqlxmqJobQueue`
/// (prod, behind the `postgres` feature).
///
/// Object-safe and synchronous for the same reasons as the other ports (see `ports.rs`).
pub trait JobQueue {
    /// Enqueue a job. Returns `Err(JobError::Full)` when the bounded capacity is exceeded
    /// (backpressure). Otherwise returns the new job's id.
    fn enqueue(&self, env: JobEnvelope) -> Result<JobId, JobError>;

    /// Claim the next queued job (FIFO), marking it `InProgress`. `Ok(None)` when the queue is
    /// empty. Phase 1 does not run a consumer; this exists for the contract + tests.
    fn consume(&self) -> Result<Option<JobRecord>, JobError>;

    /// Ack a job as done.
    fn mark_done(&self, id: JobId) -> Result<(), JobError>;

    /// Record a failed attempt: increments `attempts` and, at `max_attempts`, dead-letters the
    /// job (so it is never redelivered). Returns the resulting status.
    fn mark_retry(&self, id: JobId) -> Result<JobStatus, JobError>;

    /// The bounded capacity (used to reason about backpressure).
    fn capacity(&self) -> usize;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn feature_extract_envelope_json_round_trips() {
        let env = JobEnvelope::FeatureExtract {
            fragment_id: FragmentId::new(),
        };
        let json = serde_json::to_string(&env).unwrap();
        // Self-describing tag present.
        assert!(json.contains("\"job\":\"feature_extract\""));
        let back: JobEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(env, back);
    }

    #[test]
    fn separate_envelope_json_round_trips() {
        let env = JobEnvelope::Separate {
            fragment_id: FragmentId::new(),
        };
        let json = serde_json::to_string(&env).unwrap();
        assert!(json.contains("\"job\":\"separate\""));
        let back: JobEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(env, back);
    }

    #[test]
    fn analyze_reference_envelope_json_round_trips() {
        let env = JobEnvelope::AnalyzeReference {
            reference_track_id: crate::reference::ReferenceTrackId::new(),
        };
        let json = serde_json::to_string(&env).unwrap();
        // Self-describing snake_case tag — the exact shape the Python worker discriminates on.
        assert!(json.contains("\"job\":\"analyze_reference\""));
        assert!(json.contains("reference_track_id"));
        let back: JobEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(env, back);
    }

    #[test]
    fn default_policy_is_five_attempts() {
        assert_eq!(RetryPolicy::default().max_attempts, 5);
    }

    #[test]
    fn backoff_is_monotonic_non_decreasing_and_capped() {
        let p = RetryPolicy::default();
        let mut last = Duration::ZERO;
        for attempt in 0..8 {
            let b = p.backoff(attempt);
            assert!(b >= last, "backoff must be non-decreasing across attempts");
            last = b;
        }
        // Cap holds even for huge attempt counts (no overflow, no runaway).
        assert_eq!(p.backoff(1000), Duration::from_millis(60_000));
    }
}
