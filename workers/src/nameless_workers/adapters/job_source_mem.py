"""InMemoryJobSource — the fake for :class:`~nameless_workers.ports.JobSource`.

A simple FIFO of job envelopes with ack/retry bookkeeping, so the run loop
(:func:`nameless_workers.runner.run_once`) can be tested without Postgres/sqlxmq. Retry re-queues the
job (bounded by ``max_attempts``, mirroring the Phase-1 ``RetryPolicy``) and dead-letters past the
ceiling so a poison job cannot loop forever.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from ..domain.models import JobEnvelope
from ..ports import JobLease


class InMemoryJobSource:
    """A FIFO job source with at-least-once semantics and a retry ceiling."""

    def __init__(self, max_attempts: int = 5) -> None:
        self._queue: deque[tuple[str, JobEnvelope, int]] = deque()  # (handle, envelope, attempts)
        self._max_attempts = max_attempts
        self._counter = 0
        self.dead_lettered: list[JobEnvelope] = []
        self.acked: list[JobEnvelope] = []

    def enqueue(self, envelope: JobEnvelope) -> str:
        """Add a job (test helper — production enqueue is the Rust control plane)."""
        self._counter += 1
        handle = f"job-{self._counter}"
        self._queue.append((handle, envelope, 0))
        return handle

    def poll(self) -> Optional[JobLease]:
        if not self._queue:
            return None
        handle, envelope, _attempts = self._queue[0]
        return JobLease(handle=handle, envelope=envelope)

    def ack(self, lease: JobLease) -> None:
        self._pop(lease.handle)
        self.acked.append(lease.envelope)

    def retry(self, lease: JobLease) -> None:
        item = self._pop(lease.handle)
        if item is None:
            return
        handle, envelope, attempts = item
        attempts += 1
        if attempts >= self._max_attempts:
            self.dead_lettered.append(envelope)  # exhausted — parked, never redelivered
        else:
            self._queue.append((handle, envelope, attempts))

    def _pop(self, handle: str) -> Optional[tuple[str, JobEnvelope, int]]:
        for i, item in enumerate(self._queue):
            if item[0] == handle:
                del self._queue[i]
                return item
        return None
