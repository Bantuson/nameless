"""Run-loop tests — ack on success, retry on failure, dead-letter ceiling, misroute handling."""

from __future__ import annotations

import pytest

from nameless_workers.adapters import InMemoryFragmentRepo, InMemoryJobSource
from nameless_workers.adapters.audio_loader_fake import InMemoryAudioLoader
from nameless_workers.adapters.embed_fake import FakeEmbedder
from nameless_workers.adapters.feature_fake import FakeFeatureExtractor
from nameless_workers.consumer import AnalyzeJobConsumer
from nameless_workers.domain.models import FeatureExtractJob, SeparateJob
from nameless_workers.runner import run_once

from .conftest import make_record

AUDIO = b"loop test audio"


def _consumer(loader, repo) -> AnalyzeJobConsumer:
    return AnalyzeJobConsumer(
        loader=loader,
        extractor=FakeFeatureExtractor(),
        embedder=FakeEmbedder(),
        repo=repo,
    )


def test_run_once_acks_on_success():
    loader = InMemoryAudioLoader()
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="aa10")
    loader.put(rec.audio_uri, AUDIO)
    repo.insert(rec)

    source = InMemoryJobSource()
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    outcome = run_once(source, _consumer(loader, repo))
    assert outcome is not None and outcome.to_state == "analyzed"
    assert len(source.acked) == 1
    assert source.poll() is None  # queue drained


def test_run_once_retries_on_failure():
    loader = InMemoryAudioLoader()  # bytes NOT registered → load fails → AnalyzeError
    repo = InMemoryFragmentRepo()
    rec = make_record(state="captured", audio_uri="bb11")
    repo.insert(rec)

    source = InMemoryJobSource(max_attempts=5)
    source.enqueue(FeatureExtractJob(fragment_id=rec.id))

    outcome = run_once(source, _consumer(loader, repo))
    assert outcome is None
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
    outcome = run_once(source, _consumer(loader, repo))
    assert outcome is None
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
    outcome = run_once(source, _consumer(loader, repo))
    assert outcome is None
    assert len(source.acked) == 1  # acked-to-drop (permanently un-analyzable)
    assert source.dead_lettered == []
    assert source.poll() is None  # not re-queued: the queue is drained, the worker survives
