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
from typing import Optional

from pydantic import ValidationError

from .consumer import AnalyzeError, AnalyzeJobConsumer
from .domain.models import AnalyzeOutcome, FeatureExtractJob
from .domain.state import IllegalTransition
from .ports import JobSource

logger = logging.getLogger("nameless_workers.runner")


def run_once(source: JobSource, consumer: AnalyzeJobConsumer) -> Optional[AnalyzeOutcome]:
    """Process at most one job. Returns the outcome on success, or ``None`` if the queue was empty
    or the job was retried/skipped."""
    lease = source.poll()
    if lease is None:
        return None

    envelope = lease.envelope
    if not isinstance(envelope, FeatureExtractJob):
        # This worker is bound to the feature-extract channel; a non-feature envelope is a misroute
        # (e.g. a Phase-8 Separate job). Ack so it does not loop here; its own consumer owns it.
        logger.warning("ignoring non-feature job on the feature worker: %r", envelope)
        source.ack(lease)
        return None

    try:
        outcome = consumer.handle(envelope)
    except AnalyzeError as exc:
        # Recoverable (load/extract/embed/persist failed, or fragment not yet present): let the
        # queue's bounded RetryPolicy retry/dead-letter. A redeliver re-enters via the idempotency path.
        logger.warning("analysis failed (will retry): %s", exc)
        source.retry(lease)
        return None
    except (IllegalTransition, ValidationError) as exc:
        # PERMANENTLY un-analyzable, not a transient fault — and unrelated to AnalyzeError:
        #   * IllegalTransition: a placed/mixed/ai-path/rejected (or concurrently-advanced) fragment is
        #     not analyzable; a retry would raise identically forever.
        #   * ValidationError: get_fragment built a FragmentRecord from a malformed DB row (NULL
        #     note_text/audio_uri/kind); the row will not heal on redelivery.
        # ACK to drop it so one poison/misrouted fragment cannot loop or crash the worker (WR-01).
        logger.error("permanently un-analyzable job, acking to drop: %s", exc)
        source.ack(lease)
        return None
    except Exception as exc:  # noqa: BLE001 - last-resort guard: an unexpected fault must not crash run_forever
        # Unknown failure (e.g. KeyError from a row vanishing between get_fragment and advance, or a
        # latent bug). Treat as retryable so the bounded ceiling/dead-letter handles it rather than
        # taking the whole loop down on a single job.
        logger.exception("unexpected error processing job; will retry: %s", exc)
        source.retry(lease)
        return None

    source.ack(lease)
    return outcome


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
    """
    import time

    idle = 0
    while True:
        outcome = run_once(source, consumer)
        if outcome is None and source.poll() is None:
            idle += 1
            if max_idle_polls is not None and idle >= max_idle_polls:
                return
            time.sleep(poll_interval_s)
        else:
            idle = 0
