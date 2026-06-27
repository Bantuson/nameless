"""Rate limiters — the throttle gate (KNOW-02), over an injected :class:`~knowledge_pipeline.ports.Clock`.

Two implementations of the :class:`~knowledge_pipeline.ports.RateLimiter` port:
  * :class:`IntervalRateLimiter` — enforces a MINIMUM interval (plus optional jitter) between requests by
    sleeping the deficit via the clock. This is the real throttle the live ingest uses to stay polite and
    dodge YouTube's 429/bot defenses (PITFALLS #2: "throttle hard — seconds between requests, jitter").
    Because it sleeps via the CLOCK port, a FakeClock test verifies the spacing in virtual time.
  * :class:`NoOpRateLimiter`     — never waits. For fixture/test paths where throttling is irrelevant.

Jitter uses an INJECTED ``random.Random`` (seedable) so even the jittered throttle is deterministic in a
test — randomness is a dependency too (testability law).
"""

from __future__ import annotations

import random
from typing import Optional

from ..ports import Clock


class IntervalRateLimiter:
    """Sleep so that consecutive ``acquire`` calls are at least ``min_interval_s`` apart (+ jitter)."""

    def __init__(
        self,
        clock: Clock,
        *,
        min_interval_s: float = 2.0,
        jitter_s: float = 0.0,
        rng: Optional[random.Random] = None,
    ) -> None:
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be >= 0")
        self._clock = clock
        self._min_interval = float(min_interval_s)
        self._jitter = max(0.0, float(jitter_s))
        self._rng = rng if rng is not None else random.Random()
        self._last_acquire: Optional[float] = None

    def acquire(self) -> None:
        """Block (via the clock) until enough time has elapsed since the previous acquire."""
        now = self._clock.monotonic()
        if self._last_acquire is None:
            # First request goes immediately; jitter still applies so a burst of clients de-syncs.
            wait = self._jitter_amount()
        else:
            elapsed = now - self._last_acquire
            wait = (self._min_interval - elapsed) + self._jitter_amount()

        if wait > 0:
            self._clock.sleep(wait)
        self._last_acquire = self._clock.monotonic()

    def _jitter_amount(self) -> float:
        return self._rng.uniform(0.0, self._jitter) if self._jitter > 0 else 0.0


class NoOpRateLimiter:
    """A throttle that never throttles — for fixture/offline paths where spacing does not matter."""

    def acquire(self) -> None:  # noqa: D401 - intentionally does nothing
        return None
