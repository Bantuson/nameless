//! In-memory job queue — proves the CAP-07 retry/backpressure/dead-letter contract without a DB.
//!
//! Backed by `Mutex<VecDeque<JobRecord>>` with a fixed capacity. The production `SqlxmqJobQueue`
//! (behind the `postgres` feature) satisfies the same [`JobQueue`] trait over a durable Postgres
//! queue; this fake models the same semantics in RAM so the contract is verified on the 4GB box.
//!
//! "Durability within process": records persist in the queue across many enqueue/consume cycles
//! until explicitly `mark_done` or dead-lettered — modelling the at-least-once contract sqlxmq
//! provides across a restart (the cross-restart proof itself is env-gated to Plan 04).

use std::collections::VecDeque;
use std::sync::Mutex;

use nameless_core::job::{
    JobEnvelope, JobError, JobId, JobQueue, JobRecord, JobStatus, RetryPolicy,
};

/// An in-memory [`JobQueue`] with bounded capacity and a configurable retry policy.
#[derive(Debug)]
pub struct InMemoryJobQueue {
    inner: Mutex<VecDeque<JobRecord>>,
    capacity: usize,
    policy: RetryPolicy,
}

impl InMemoryJobQueue {
    /// Create a queue with `capacity` slots and the default retry policy (5 attempts).
    pub fn new(capacity: usize) -> Self {
        Self::with_policy(capacity, RetryPolicy::default())
    }

    /// Create a queue with an explicit retry policy (used by retry-ceiling tests).
    pub fn with_policy(capacity: usize, policy: RetryPolicy) -> Self {
        InMemoryJobQueue {
            inner: Mutex::new(VecDeque::new()),
            capacity,
            policy,
        }
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, VecDeque<JobRecord>>, JobError> {
        self.inner
            .lock()
            .map_err(|_| JobError::Backend {
                msg: "job queue mutex poisoned".into(),
            })
    }

    /// Count of jobs still occupying a slot (anything not Done/DeadLettered).
    fn live_count(q: &VecDeque<JobRecord>) -> usize {
        q.iter()
            .filter(|r| !matches!(r.status, JobStatus::Done | JobStatus::DeadLettered))
            .count()
    }
}

impl JobQueue for InMemoryJobQueue {
    fn enqueue(&self, env: JobEnvelope) -> Result<JobId, JobError> {
        let mut q = self.lock()?;
        // Backpressure: refuse when the live set is at capacity.
        if Self::live_count(&q) >= self.capacity {
            return Err(JobError::Full);
        }
        let id = JobId::new();
        q.push_back(JobRecord {
            id,
            envelope: env,
            attempts: 0,
            status: JobStatus::Queued,
        });
        Ok(id)
    }

    fn consume(&self) -> Result<Option<JobRecord>, JobError> {
        let mut q = self.lock()?;
        // FIFO: find the first Queued/Failed (retryable) record, mark InProgress, return a copy.
        for rec in q.iter_mut() {
            if matches!(rec.status, JobStatus::Queued | JobStatus::Failed) {
                rec.status = JobStatus::InProgress;
                return Ok(Some(rec.clone()));
            }
        }
        Ok(None)
    }

    fn mark_done(&self, id: JobId) -> Result<(), JobError> {
        let mut q = self.lock()?;
        let rec = q
            .iter_mut()
            .find(|r| r.id == id)
            .ok_or(JobError::NotFound(id))?;
        rec.status = JobStatus::Done;
        Ok(())
    }

    fn mark_retry(&self, id: JobId) -> Result<JobStatus, JobError> {
        let mut q = self.lock()?;
        let rec = q
            .iter_mut()
            .find(|r| r.id == id)
            .ok_or(JobError::NotFound(id))?;
        rec.attempts += 1;
        // Dead-letter once attempts reach the policy ceiling — never redelivered (bounds retries).
        if rec.attempts >= self.policy.max_attempts {
            rec.status = JobStatus::DeadLettered;
        } else {
            rec.status = JobStatus::Failed;
        }
        Ok(rec.status)
    }

    fn capacity(&self) -> usize {
        self.capacity
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use nameless_core::fragment::FragmentId;

    fn feat() -> JobEnvelope {
        JobEnvelope::FeatureExtract {
            fragment_id: FragmentId::new(),
        }
    }

    #[test]
    fn fifo_order() {
        let q = InMemoryJobQueue::new(10);
        let a = q.enqueue(feat()).unwrap();
        let b = q.enqueue(feat()).unwrap();
        assert_eq!(q.consume().unwrap().unwrap().id, a);
        assert_eq!(q.consume().unwrap().unwrap().id, b);
        // Nothing retryable left (both InProgress).
        assert!(q.consume().unwrap().is_none());
    }

    #[test]
    fn backpressure_at_capacity() {
        let q = InMemoryJobQueue::new(2);
        q.enqueue(feat()).unwrap();
        q.enqueue(feat()).unwrap();
        match q.enqueue(feat()) {
            Err(JobError::Full) => {}
            other => panic!("expected Full, got {other:?}"),
        }
    }

    #[test]
    fn done_frees_a_capacity_slot() {
        let q = InMemoryJobQueue::new(1);
        let a = q.enqueue(feat()).unwrap();
        assert!(matches!(q.enqueue(feat()), Err(JobError::Full)));
        q.mark_done(a).unwrap();
        // Slot freed → enqueue succeeds again.
        assert!(q.enqueue(feat()).is_ok());
    }

    #[test]
    fn retry_ceiling_dead_letters_and_is_bounded() {
        let policy = RetryPolicy {
            max_attempts: 5,
            base_backoff_ms: 1,
        };
        let q = InMemoryJobQueue::with_policy(10, policy);
        let id = q.enqueue(feat()).unwrap();

        // A trivial consumer loop that always "fails" the job: retry until dead-lettered, asserting
        // it terminates in a bounded number of steps (no infinite redelivery).
        let mut status = JobStatus::Queued;
        let mut iterations = 0;
        while !matches!(status, JobStatus::DeadLettered) {
            iterations += 1;
            assert!(iterations <= policy.max_attempts, "retries must be bounded");
            let rec = q.consume().unwrap().expect("job should redeliver until dead-lettered");
            assert_eq!(rec.id, id);
            status = q.mark_retry(rec.id).unwrap();
        }
        assert_eq!(iterations, policy.max_attempts);

        // Dead-lettered job is never redelivered.
        assert!(q.consume().unwrap().is_none());
    }

    #[test]
    fn mark_unknown_job_is_not_found() {
        let q = InMemoryJobQueue::new(1);
        assert!(matches!(
            q.mark_done(JobId::new()),
            Err(JobError::NotFound(_))
        ));
    }
}
