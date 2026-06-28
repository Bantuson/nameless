"""Pure tonal-balance math — band energies + normalization to ratios."""

from __future__ import annotations

import numpy as np
import pytest

from nameless_workers.pure.tonal_balance import (
    DEFAULT_BAND_EDGES_HZ,
    band_energies,
    normalize_to_tonal_balance,
    tonal_balance_from_spectrum,
)


def test_band_energies_sums_power_into_the_right_bands():
    # One bin per band, each at a centre frequency comfortably inside its band.
    freqs = [60.0, 300.0, 1000.0, 3000.0, 10000.0]
    magnitude = [2.0, 0.0, 0.0, 0.0, 0.0]  # power = magnitude**2 → 4 in the low band
    energies = band_energies(freqs, magnitude)
    assert energies == pytest.approx([4.0, 0.0, 0.0, 0.0, 0.0])


def test_band_energies_includes_the_top_edge_in_the_final_band():
    # A bin exactly at the top edge (20 kHz) must land in the last band, not be dropped.
    freqs = [DEFAULT_BAND_EDGES_HZ[-1]]
    magnitude = [3.0]
    energies = band_energies(freqs, magnitude)
    assert energies[-1] == pytest.approx(9.0)
    assert sum(energies[:-1]) == pytest.approx(0.0)


def test_band_energies_ignores_bins_outside_the_outer_edges():
    freqs = [5.0, 25000.0]  # below 20 Hz and above 20 kHz
    magnitude = [10.0, 10.0]
    assert band_energies(freqs, magnitude) == pytest.approx([0.0] * 5)


def test_normalize_gives_ratios_summing_to_one():
    tb = normalize_to_tonal_balance([4.0, 1.0, 1.0, 1.0, 1.0])
    assert tb.total() == pytest.approx(1.0)
    assert tb.low == pytest.approx(0.5)  # 4 / 8


def test_normalize_silence_is_all_zeros_not_nan():
    tb = normalize_to_tonal_balance([0.0, 0.0, 0.0, 0.0, 0.0])
    assert tb.bands() == [0.0, 0.0, 0.0, 0.0, 0.0]
    assert tb.total() == 0.0


def test_normalize_rejects_wrong_length_and_negatives():
    with pytest.raises(ValueError):
        normalize_to_tonal_balance([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        normalize_to_tonal_balance([1.0, -1.0, 1.0, 1.0, 1.0])


def test_bright_vs_warm_spectrum_tilts_the_balance():
    freqs = [60.0, 300.0, 1000.0, 3000.0, 10000.0]
    bright = tonal_balance_from_spectrum(freqs, [0.0, 0.0, 0.0, 1.0, 2.0])
    warm = tonal_balance_from_spectrum(freqs, [2.0, 1.0, 0.0, 0.0, 0.0])
    # The bright spectrum's energy concentrates high; the warm one's, low.
    assert bright.high > bright.low
    assert warm.low > warm.high


def test_band_energies_rejects_mismatched_arrays():
    with pytest.raises(ValueError):
        band_energies([1.0, 2.0], [1.0])
    # numpy arrays accepted too (not just lists).
    assert band_energies(np.array([60.0]), np.array([1.0]))[0] == pytest.approx(1.0)
