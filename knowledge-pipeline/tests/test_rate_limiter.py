"""Rate-limiter tests (KNOW-02 throttle) — verified in VIRTUAL time via the FakeClock, no real sleep."""

from __future__ import annotations

import random

from knowledge_pipeline.adapters import FakeClock, IntervalRateLimiter, NoOpRateLimiter


def test_first_acquire_does_not_sleep():
    clock = FakeClock()
    limiter = IntervalRateLimiter(clock, min_interval_s=2.0)
    limiter.acquire()
    assert clock.total_slept == 0.0


def test_back_to_back_acquires_sleep_the_full_interval():
    clock = FakeClock()
    limiter = IntervalRateLimiter(clock, min_interval_s=2.0)
    for _ in range(5):
        limiter.acquire()
    # 5 acquires ⇒ 4 gaps of 2.0s each, all in virtual time.
    assert clock.total_slept == 8.0
    assert clock.sleeps == [2.0, 2.0, 2.0, 2.0]


def test_work_between_requests_reduces_the_wait():
    clock = FakeClock()
    limiter = IntervalRateLimiter(clock, min_interval_s=2.0)
    limiter.acquire()
    clock.advance(1.5)   # "work" took 1.5s of virtual time (not a throttle sleep)
    limiter.acquire()
    # only the 0.5s deficit needs sleeping
    assert clock.total_slept == 0.5


def test_slow_work_means_no_sleep():
    clock = FakeClock()
    limiter = IntervalRateLimiter(clock, min_interval_s=2.0)
    limiter.acquire()
    clock.advance(5.0)   # work already exceeded the interval
    limiter.acquire()
    assert clock.total_slept == 0.0


def test_jitter_is_deterministic_with_seeded_rng():
    clock = FakeClock()
    limiter = IntervalRateLimiter(clock, min_interval_s=1.0, jitter_s=0.5, rng=random.Random(42))
    limiter.acquire()  # first acquire applies jitter only
    limiter.acquire()
    # reproducible: same seed ⇒ same total slept
    clock2 = FakeClock()
    limiter2 = IntervalRateLimiter(clock2, min_interval_s=1.0, jitter_s=0.5, rng=random.Random(42))
    limiter2.acquire()
    limiter2.acquire()
    assert clock.sleeps == clock2.sleeps
    assert clock.total_slept >= 1.0  # at least the base interval


def test_noop_limiter_never_sleeps():
    limiter = NoOpRateLimiter()
    for _ in range(10):
        limiter.acquire()  # no clock, no time — purely a pass-through
