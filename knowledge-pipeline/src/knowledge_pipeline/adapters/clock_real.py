"""SystemClock — the REAL :class:`~knowledge_pipeline.ports.Clock` (wall + monotonic time, real sleep).

Trivial, but it exists so the pipeline NEVER calls ``datetime.now()`` / ``time.sleep()`` directly: time
is injected like every other dependency, and production simply uses this. ``now()`` is timezone-aware
UTC so snapshot retrieval dates are unambiguous across machines.
"""

from __future__ import annotations

import datetime as _dt
import time


class SystemClock:
    """Real time. ``now`` is UTC-aware; ``sleep`` actually blocks (used by the live throttle)."""

    def now(self) -> _dt.datetime:
        return _dt.datetime.now(_dt.timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)
