"""Run-loop tests — ack on success, retry on failure, dead-letter ceiling, misroute handling."""

from __future__ import annotations

from collections import deque
from typing import Optional

import pytest

from nameless_workers.adapters import InMemoryFragmentRepo, InMemoryJobSource
from nameless_workers.adapters.audio_loader_fake import InMemoryAudioLoader
from nameless_workers.adapters.embed_fake import FakeEmbedder
from nameless_workers.adapters.feature_fake import FakeFeatureExtractor
from nameless_workers.consumer import AnalyzeJobConsumer
from nameless_workers.domain.models import FeatureExtractJob, SeparateJob
from nameless_workers.ports import JobLease
from nameless_workers.runner import RunStatus, run_forever, run_once

from .conftest import make_record

AUDIO = b"loop test audio"


def _consumer(loader, repo) -> AnalyzeJobConsumer:
    return AnalyzeJobConsumer(
        loader=loader,
        extractor=FakeFeatureExtractor(),
        embedder=FakeEmbedder(),
        repo=repo,
    )


class DestructivePollJobSource:
    """A JobSource whose ``poll()`` claims DESTRUCTIVELY — the real ``SELECT … FOR UPDATE SKIP
    LOCKED`` semantics the production poller has, unlike the non-destructive ``InMemoryJobSource``
    (which peeks ``_queue[0]`` and so masks the WR-02 double-poll bug).

    A claimed job leaves the visible queue and lives in ``_inflight`` until ``ack``/``retry`` decides
    its fate. A job that is polled but never acked/retried is therefore LEAKED — its lease dangles
    (exactly what a phantom second ``poll()`` per cycle would do). ``poll_count`` counts every claim.
    """

    def __init__(self) -> None:
        self._queue: deque[tuple[str, object]] = deque()
        self._inflight: dict[str, object] = {}
        self._counter = 0
        self.poll_count = 0
        self.acked: list[object] = []

    def enqueue(self, envelope) -> None:
        self._counter += 1
        self._queue.append((f"job-{self._counter}", envelope))

    def poll(self) -> Optional[JobLease]:
        self.poll_count += 1
        if not self._queue:
            return None
        handle, envelope = self._queue.popleft()  # destructive claim — gone from the visible queue
        self._inflight[handle] = envelope
        return JobLease(handle=handle, envelope=envelope)

    def ack(self, lease: JobLease) -> None:
        self._inflight.pop(lease.handle, None)
        self.acked.append(lease.envelope)

    def retry(self, lease: JobLease) -> None:
        env = self._inflight.pop(lease.handle, None)
        if env is not None:
            self._queue.append((lease.handle, env))  # back to the queue for another attempt

    @property
    def leaked(self) -> list:
        """Jobs claimed but neither acked nor returned — dangling leases (the WR-02 symptom)."""
        return list(self._inflight.values())


def test_run_once_acks_on_success():
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="aa10")
    loader.put(rec.audio_uri, AUDIO)
    repo.insert(rec)

    source = InMemoryJobSource()
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    result = run_once(source, _consumer(loader, repo))
    assert result.status is RunStatus.DID_WORK
    assert result.outcome is not None and result.outcome.to_state == "analyzed"
    assert len(source.acked) == 1
    assert source.poll() is None  # queue drained


def test_run_once_retries_on_failure():
    loader = InMemoryAudioLoader()  # bytes NOT registered → load fails → AnalyzeError
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="bb11")
    repo.insert(rec)

    source = InMemoryJobSource(max_attempts=5)
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    result = run_once(source, _consumer(loader, repo))
    assert result.status is RunStatus.RETRIED
    assert result.outcome is None
    assert source.acked == []
    # Re-queued for another attempt (not yet dead-lettered).
    assert source.poll() is not None
    assert source.dead_lettered == []


def test_poison_job_dead_letters_after_the_ceiling():
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="cc12")
    repo.insert(rec)

    source = InMemoryJobSource(max_attempts=3)
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    consumer = _consumer(loader, repo)
    # Three failing attempts → parked, never redelivered (bounded retry, DoS-safe).
    for _ in range(3):
        run_once(source, consumer)
    assert source.poll() is None
    assert len(source.dead_lettered) == 1


def test_non_feature_job_is_acked_not_processed():
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    source = InMemoryJobSource()
    from uuid import uuid4

    source.enqueue(SeparateJob(fragment_id=uuid4()))  # a Phase-8 job misrouted to this worker
    result = run_once(source, _consumer(loader, repo))
    assert result.status is RunStatus.DID_WORK  # absorbed (acked), not idle
    assert result.outcome is None
    assert len(source.acked) == 1  # acked so it does not loop here


def test_poison_unanalyzable_fragment_is_acked_not_crashed():
    """WR-01: a job targeting a structurally un-analyzable fragment (already ``placed``) makes
    ``consumer.handle`` raise ``IllegalTransition`` — NOT an ``AnalyzeError``. The run loop must catch
    it and ACK (drop) rather than let it escape and crash ``run_forever``. It will never succeed on
    retry, so acking is correct (and it is not re-queued or dead-lettered)."""
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    rec = make_record(state="placed", audio_uri="dd13")  # not analyzable: no PLACED -> ANALYZE edge
    loader.put(rec.audio_uri, AUDIO)
    repo.insert(rec)

    source = InMemoryJobSource(max_attempts=5)
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    # Must NOT raise — the poison fragment is absorbed, not propagated.
    result = run_once(source, _consumer(loader, repo))
    assert result.status is RunStatus.DID_WORK  # resolved by acking-to-drop, not crashed
    assert result.outcome is None
    assert len(source.acked) == 1  # acked-to-drop (permanently un-analyzable)
    assert source.dead_lettered == []
    assert source.poll() is None  # not re-queued: the queue is drained, the worker survives


def test_run_forever_does_not_leak_a_second_lease_under_destructive_poll():
    """WR-02: ``run_forever`` must drive its idle check off the SINGLE claim ``run_once`` already made,
    never a phantom second ``source.poll()``. Under destructive (real) claim semantics, that second
    poll would claim a second job and discard its lease — leaking it. With two jobs queued, both must
    be processed and NONE leaked; and the only polls are the two claims + one empty terminating poll."""
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    source = DestructivePollJobSource()
    for uri in ("e1", "e2"):
        rec = make_record(state="captured", audio_uri=uri)
        loader.put(rec.audio_uri, AUDIO)
        repo.insert(rec)
        source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    run_forever(source, _consumer(loader, repo), poll_interval_s=0, max_idle_polls=1)

    assert len(source.acked) == 2  # BOTH jobs ran — neither was claimed-and-discarded
    assert source.leaked == []  # no dangling lease
    # Exactly: claim job1, claim job2, one empty poll that trips max_idle_polls. No double-poll.
    assert source.poll_count == 3


def test_run_forever_does_not_hot_loop_on_a_retried_job(monkeypatch):
    """WR-02 (second half): a job that keeps failing is RETRIED, and ``run_forever`` must pace each
    retry by ``poll_interval_s`` rather than spinning. It must still terminate: the source's retry
    ceiling dead-letters the job, after which polls go IDLE and ``max_idle_polls`` stops the loop."""
    loader = InMemoryAudioLoader()  # bytes NOT registered → every attempt fails → AnalyzeError/RETRIED
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="ff14")
    repo.insert(rec)

    source = InMemoryJobSource(max_attempts=3)
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    sleeps: list[float] = []
    import time as _time  # run_forever does a function-local `import time`; same module singleton

    monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))

    run_forever(source, _consumer(loader, repo), poll_interval_s=0.5, max_idle_polls=1)

    # The failing job is dead-lettered after the ceiling (not looped forever).
    assert len(source.dead_lettered) == 1
    # Each retry paced by poll_interval (3 attempts) plus the final idle sleep — never a tight spin.
    assert sleeps and all(s == 0.5 for s in sleeps)
