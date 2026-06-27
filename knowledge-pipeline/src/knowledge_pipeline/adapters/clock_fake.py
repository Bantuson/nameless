"""FakeClock — the deterministic :class:`~knowledge_pipeline.ports.Clock` for tests (VIRTUAL time).

This is what makes throttling testable WITHOUT real time. ``sleep(seconds)`` does not block — it ADVANCES
a virtual monotonic counter and records the slept duration. So a test can drive the rate limiter through
many ``acquire`` calls and assert "the limiter slept ~min_interval between requests" in microseconds,
deterministically, with no flakiness and no wall-clock dependence.

``now()`` returns a fixed (advanceable) wall time, so snapshot ``retrieval_date`` values in tests are
reproducible (``snapshot_record`` takes ``now`` as an argument — this is the thing that supplies it).
"""

from __future__ import annotations

import datetime as _dt


class FakeClock:
    """Virtual-time clock. ``sleep`` advances time instead of waiting; every sleep is recorded."""

    def __init__(
        self,
        *,
        start_wall: _dt.datetime | None = None,
        start_monotonic: float = 0.0,
    ) -> None:
        self._wall = start_wall or _dt.datetime(2026, 6, 27, 12, 0, 0, tzinfo=_dt.timezone.utc)
        self._mono = float(start_monotonic)
        self.sleeps: list[float] = []  # every slept duration, in call order (test assertions read this)

    # ---- Clock port ----
    def now(self) -> _dt.datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._mono

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            seconds = 0.0
        self._mono += seconds
        self._wall = self._wall + _dt.timedelta(seconds=seconds)
        self.sleeps.append(seconds)

    # ---- test seam: advance time without a "sleep" (e.g. simulate real work taking N seconds) ----
    def advance(self, seconds: float) -> None:
        """Advance virtual time as if work happened — NOT recorded as a throttle sleep."""
        self._mono += max(0.0, seconds)
        self._wall = self._wall + _dt.timedelta(seconds=max(0.0, seconds))

    @property
    def total_slept(self) -> float:
        return sum(self.sleeps)
