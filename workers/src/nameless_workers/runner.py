"""The worker run loop — pulls feature-extract jobs from a :class:`JobSource` and runs the consumer.

This is the thin driver around :class:`~nameless_workers.consumer.AnalyzeJobConsumer`. It is kept
separate (and itself port-driven) so it is testable with :class:`InMemoryJobSource`: ack on success,
retry on a recoverable :class:`AnalyzeError` (the queue's bounded retry/dead-letter then applies — the
same RetryPolicy shape Phase 1 defined).

Cross-language note: in production the "source" may be the Rust sqlxmq ``JobRunner`` invoking the
Python ``analyze`` entrypoint per job (see ``cli.py``), in which case this loop is not used at all —
the consumer is. Both bindings call the SAME :meth:`AnalyzeJobConsumer.handle`. See workers/README.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import ValidationError

from .consumer import AnalyzeError, AnalyzeJobConsumer
from .domain.models import AnalyzeOutcome, FeatureExtractJob
from .domain.state import IllegalTransition
from .ports import JobSource

logger = logging.getLogger("nameless_workers.runner")


class RunStatus(str, Enum):
    """What one :func:`run_once` claim did — the signal :func:`run_forever` drives its idle policy off.

    Distinguishing these from a *single* ``poll()`` is the WR-02 fix: previously ``run_forever`` polled
    a second time to tell "queue empty" apart from "job retried", which under a real claim-semantics
    ``poll()`` (``SELECT … FOR UPDATE SKIP LOCKED``) claimed-and-discarded a second job's lease.
    """

    IDLE = "idle"  # the queue was empty — nothing was claimed this cycle
    DID_WORK = "did_work"  # a job was claimed and resolved (analyzed, or acked-to-drop) — drain on
    RETRIED = "retried"  # a job was claimed but deferred for another attempt (do not hot-loop on it)


@dataclass(frozen=True)
class RunResult:
    """The outcome of one :func:`run_once` cycle: a :class:`RunStatus` plus the analysis outcome
    (present only on a successful ``DID_WORK`` analysis; ``None`` for idle/retry/drop/misroute)."""

    status: RunStatus
    outcome: Optional[AnalyzeOutcome] = None


def run_once(source: JobSource, consumer: AnalyzeJobConsumer) -> RunResult:
    """Process at most one job, claiming it with a SINGLE :meth:`JobSource.poll`.

    Returns a :class:`RunResult` whose :class:`RunStatus` tells the caller whether the queue was empty
    (``IDLE``), a job was processed/dropped (``DID_WORK``), or a job was deferred for retry
    (``RETRIED``) — without ever polling a second time (WR-02).
    """
    lease = source.poll()
    if lease is None:
        return RunResult(RunStatus.IDLE)

    envelope = lease.envelope
    if not isinstance(envelope, FeatureExtractJob):
        # This worker is bound to the feature-extract channel; a non-feature envelope is a misroute
        # (e.g. a Phase-8 Separate job). Ack so it does not loop here; its own consumer owns it.
        logger.warning("ignoring non-feature job on the feature worker: %r", envelope)
        source.ack(lease)
        return RunResult(RunStatus.DID_WORK)

    try:
        outcome = consumer.handle(envelope)
    except AnalyzeError as exc:
        # Recoverable (load/extract/embed/persist failed, or fragment not yet present): let the
        # queue's bounded RetryPolicy retry/dead-letter. A redeliver re-enters via the idempotency path.
        logger.warning("analysis failed (will retry): %s", exc)
        source.retry(lease)
        return RunResult(RunStatus.RETRIED)
    except (IllegalTransition, ValidationError) as exc:
        # PERMANENTLY un-analyzable, not a transient fault — and unrelated to AnalyzeError:
        #   * IllegalTransition: a placed/mixed/ai-path/rejected (or concurrently-advanced) fragment is
        #     not analyzable; a retry would raise identically forever.
        #   * ValidationError: get_fragment built a FragmentRecord from a malformed DB row (NULL
        #     note_text/audio_uri/kind); the row will not heal on redelivery.
        # ACK to drop it so one poison/misrouted fragment cannot loop or crash the worker (WR-01).
        logger.error("permanently un-analyzable job, acking to drop: %s", exc)
        source.ack(lease)
        return RunResult(RunStatus.DID_WORK)
    except Exception as exc:  # noqa: BLE001 - last-resort guard: an unexpected fault must not crash run_forever
        # Unknown failure (e.g. KeyError from a row vanishing between get_fragment and advance, or a
        # latent bug). Treat as retryable so the bounded ceiling/dead-letter handles it rather than
        # taking the whole loop down on a single job.
        logger.exception("unexpected error processing job; will retry: %s", exc)
        source.retry(lease)
        return RunResult(RunStatus.RETRIED)

    source.ack(lease)
    return RunResult(RunStatus.DID_WORK, outcome)


def run_forever(
    source: JobSource,
    consumer: AnalyzeJobConsumer,
    *,
    poll_interval_s: float = 1.0,
    max_idle_polls: Optional[int] = None,
) -> None:
    """Loop: drain the queue, sleeping ``poll_interval_s`` when idle.

    ``max_idle_polls`` (if set) stops after that many consecutive empty polls — useful for a bounded
    batch run or a test. ``None`` runs until interrupted.

    The idle counter is driven off the SINGLE claim :func:`run_once` already made (its
    :class:`RunStatus`), never a second :meth:`JobSource.poll` — so no extra job's lease is claimed and
    discarded per cycle (WR-02). A ``RETRIED`` job is paced by ``poll_interval_s`` too (so a re-queued
    job cannot hot-loop), but is not counted as idle since there is still work in flight.
    """
    import time

    idle = 0
    while True:
        result = run_once(source, consumer)
        if result.status is RunStatus.IDLE:
            idle += 1
            if max_idle_polls is not None and idle >= max_idle_polls:
                return
            time.sleep(poll_interval_s)
        elif result.status is RunStatus.RETRIED:
            # A job was claimed but deferred. Don't spin re-claiming it; pace by poll_interval. Not
            # "idle" (there is work), so it does not trip max_idle_polls — the source's retry ceiling
            # eventually dead-letters a persistently-failing job, after which polls go IDLE and stop.
            time.sleep(poll_interval_s)
        else:  # DID_WORK — a job was processed/dropped; there may be more, so drain immediately.
            idle = 0
