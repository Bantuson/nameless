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

from .consumer import AnalyzeError, AnalyzeJobConsumer
from .domain.models import AnalyzeOutcome, FeatureExtractJob
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
        logger.warning("analysis failed (will retry): %s", exc)
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
