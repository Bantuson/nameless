"""Fake vibe describer — deterministic, grounded in numbers, and never melodic."""

from __future__ import annotations

from nameless_workers.adapters.vibe_describer_fake import FakeVibeDescriber
from nameless_workers.domain.reference import NonMelodicFeatures, TonalBalance


def _features(*, tempo: float, lufs: float, width: float, low: float, high: float) -> NonMelodicFeatures:
    # Spread the remaining energy across the middle bands; only low/high tilt matters for the test.
    mid_each = max(0.0, (1.0 - low - high) / 3.0)
    return NonMelodicFeatures(
        tonal_balance=TonalBalance(low=low, low_mid=mid_each, mid=mid_each, high_mid=mid_each, high=high),
        stereo_width=width,
        lufs=lufs,
        tempo_bpm_min=tempo - 2,
        tempo_bpm_max=tempo + 2,
        genre="amapiano",
        sample_rate=44_100,
        duration_s=180.0,
    )


def test_deterministic_for_the_same_features():
    d = FakeVibeDescriber()
    f = _features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1)
    assert d.describe(f) == d.describe(f)


def test_mentions_no_melodic_terms():
    d = FakeVibeDescriber()
    text = d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1)).lower()
    for forbidden in ("melody", "chord", "key", "note", "pitch", "scale"):
        assert forbidden not in text, f"vibe prose must not mention {forbidden!r}: {text!r}"


def test_tempo_drives_energy_word():
    d = FakeVibeDescriber()
    fast = d.describe(_features(tempo=128, lufs=-9, width=0.5, low=0.3, high=0.2))
    slow = d.describe(_features(tempo=70, lufs=-12, width=0.2, low=0.3, high=0.2))
    assert "driving" in fast
    assert "slow" in slow


def test_tonal_tilt_drives_the_balance_phrase():
    d = FakeVibeDescriber()
    warm = d.describe(_features(tempo=110, lufs=-9, width=0.5, low=0.6, high=0.05))
    bright = d.describe(_features(tempo=110, lufs=-9, width=0.5, low=0.05, high=0.6))
    assert "bass-forward" in warm
    assert "airy" in bright
