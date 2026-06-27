"""Krumhansl-Schmuckler key estimation — pure-function correctness tests."""

from __future__ import annotations

import numpy as np
import pytest

from nameless_workers.pure.key import (
    _MAJOR_PROFILE,
    _MINOR_PROFILE,
    _PITCH_NAMES,
    estimate_key,
)


def _rotate(profile: np.ndarray, tonic: int) -> list[float]:
    """Build a chroma whose pitch-class energies equal `profile` placed at `tonic`."""
    rotation = (np.arange(12) - tonic) % 12
    return profile[rotation].tolist()


def test_major_profile_resolves_to_its_tonic_major():
    # Feeding the C-major template back in must resolve to C:maj with perfect correlation.
    key = estimate_key(_MAJOR_PROFILE.tolist())
    assert key.name == "C:maj"
    assert key.tonic_pc == 0
    assert key.mode == "maj"
    assert key.correlation == pytest.approx(1.0, abs=1e-9)


def test_minor_profile_resolves_to_its_tonic_minor():
    key = estimate_key(_MINOR_PROFILE.tolist())
    assert key.name == "C:min"
    assert key.mode == "min"
    assert key.correlation == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("tonic", list(range(12)))
def test_transposing_the_input_transposes_the_estimate(tonic):
    # The major template placed at every tonic must resolve to that tonic's major key.
    chroma = _rotate(_MAJOR_PROFILE, tonic)
    key = estimate_key(chroma)
    assert key.tonic_pc == tonic
    assert key.mode == "maj"
    assert key.name == f"{_PITCH_NAMES[tonic]}:maj"


def test_c_major_triad_energy_resolves_to_c_major():
    # Energy concentrated on C, E, G (a C-major triad) reads as C:maj.
    chroma = np.full(12, 0.05)
    for pc in (0, 4, 7):
        chroma[pc] = 1.0
    key = estimate_key(chroma.tolist())
    assert key.name == "C:maj"


def test_flat_chroma_is_ambiguous_zero_correlation():
    # A perfectly flat chroma (silence / no tonal centre) has no key — correlation collapses to 0.
    key = estimate_key(np.ones(12).tolist())
    assert key.correlation == pytest.approx(0.0, abs=1e-12)


def test_wrong_length_raises():
    with pytest.raises(ValueError):
        estimate_key([1.0, 2.0, 3.0])
