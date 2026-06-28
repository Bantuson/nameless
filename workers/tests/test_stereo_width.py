"""Pure stereo-width math — mid/side energy ratio + L/R correlation."""

from __future__ import annotations

import numpy as np
import pytest

from nameless_workers.pure.stereo_width import (
    lr_correlation,
    mid_side,
    stereo_width_from_mono,
    stereo_width_ratio,
)


def test_mid_side_transform():
    left = [1.0, 2.0, 3.0]
    right = [1.0, 0.0, -1.0]
    mid, side = mid_side(left, right)
    assert mid.tolist() == pytest.approx([1.0, 1.0, 1.0])
    assert side.tolist() == pytest.approx([0.0, 1.0, 2.0])


def test_mono_signal_has_zero_width():
    sig = np.sin(np.linspace(0, 6.28, 256)).tolist()
    # L == R → side energy 0 → width 0.
    assert stereo_width_ratio(sig, sig) == pytest.approx(0.0)
    assert stereo_width_from_mono(sig) == 0.0


def test_anti_phase_is_maximally_wide():
    sig = np.sin(np.linspace(0, 6.28, 256))
    # L = sig, R = -sig → mid = 0, side = sig → width 1.0.
    assert stereo_width_ratio(sig.tolist(), (-sig).tolist()) == pytest.approx(1.0)


def test_one_channel_silent_is_half_width():
    sig = np.sin(np.linspace(0, 6.28, 256))
    zeros = np.zeros_like(sig)
    # mid = sig/2, side = sig/2 → equal energy → width 0.5.
    assert stereo_width_ratio(sig.tolist(), zeros.tolist()) == pytest.approx(0.5)


def test_silence_is_zero_width_not_nan():
    z = [0.0] * 64
    assert stereo_width_ratio(z, z) == 0.0


def test_lr_correlation_identity_antiphase_and_undefined():
    sig = np.sin(np.linspace(0, 6.28, 256))
    assert lr_correlation(sig.tolist(), sig.tolist()) == pytest.approx(1.0)
    assert lr_correlation(sig.tolist(), (-sig).tolist()) == pytest.approx(-1.0)
    # A constant (zero-variance) channel → correlation undefined → 0.
    assert lr_correlation([1.0] * 8, sig[:8].tolist()) == 0.0


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        stereo_width_ratio([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        mid_side([1.0], [1.0, 2.0])
