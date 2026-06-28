"""Tonal balance — coarse multiband energy ratios. Pure functions, no librosa, no I/O.

"Tonal balance" here is a *mix* descriptor: how a track's energy is distributed across broad
frequency regions (is it bass-heavy? bright?). It is deliberately COARSE — the continuous spectrum is
folded into 5 wide bands, which destroys any note/pitch information (a melody lives in the fine
structure these bands average over). That coarseness is exactly why tonal balance is a safe
non-melodic conditioning target: you cannot reconstruct a tune from 5 numbers (PITFALLS.md Pitfall 5,
ARCHITECTURE.md Pattern 2).

These functions take arrays the caller already computed (an FFT magnitude/power spectrum + its
frequency axis). The real analyzer gets those from ``librosa`` (env-gated); the math here is pure and
fully testable with hand-built numpy arrays.

LEARNING: band energy from a magnitude spectrum is ``sum(magnitude**2)`` over the bins whose centre
frequency falls in ``[lo, hi)`` — i.e. the power in that region. Normalizing the five band powers so
they sum to 1 gives a scale-invariant *shape* (loud and quiet mixes with the same balance map to the
same ratios), which is what makes it comparable across tracks.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from ..domain.reference import TonalBalance

# Five bands → six edges (Hz). Sub / body / presence / definition / air. Coarse on purpose.
DEFAULT_BAND_EDGES_HZ: tuple[float, ...] = (20.0, 120.0, 500.0, 2000.0, 6000.0, 20000.0)


def band_energies(
    freqs: Sequence[float],
    magnitude: Sequence[float],
    edges_hz: Sequence[float] = DEFAULT_BAND_EDGES_HZ,
) -> list[float]:
    """Sum the spectral *power* (``magnitude**2``) into the bands defined by ``edges_hz``.

    ``freqs`` and ``magnitude`` are parallel arrays (e.g. one FFT frame, or an averaged spectrum).
    Returns ``len(edges_hz) - 1`` band powers, in low→high order. Bins outside the outer edges are
    ignored. Each band is ``[lo, hi)`` (upper-exclusive) except the last, which is ``[lo, hi]`` so the
    Nyquist/top bin isn't dropped.
    """
    f = np.asarray(freqs, dtype=np.float64)
    power = np.asarray(magnitude, dtype=np.float64) ** 2
    if f.shape != power.shape:
        raise ValueError(f"freqs and magnitude must match: {f.shape} vs {power.shape}")

    edges = list(edges_hz)
    out: list[float] = []
    n_bands = len(edges) - 1
    for i in range(n_bands):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bands - 1:
            mask = (f >= lo) & (f <= hi)  # include the top edge in the final band
        else:
            mask = (f >= lo) & (f < hi)
        out.append(float(power[mask].sum()))
    return out


def normalize_to_tonal_balance(energies: Sequence[float]) -> TonalBalance:
    """Normalize five band energies to ratios that sum to 1, as a :class:`TonalBalance`.

    Expects exactly 5 non-negative band energies (low→high). An all-zero / silent input maps to all
    zeros (the only honest answer — there is no balance to report), which the model accepts.
    """
    e = np.asarray(energies, dtype=np.float64)
    if e.shape != (5,):
        raise ValueError(f"expected 5 band energies (low→high), got shape {e.shape}")
    if np.any(e < 0):
        raise ValueError("band energies must be non-negative")
    total = float(e.sum())
    ratios = (e / total) if total > 0 else e  # silence → zeros, not a divide-by-zero
    low, low_mid, mid, high_mid, high = (float(x) for x in ratios)
    return TonalBalance(low=low, low_mid=low_mid, mid=mid, high_mid=high_mid, high=high)


def tonal_balance_from_spectrum(
    freqs: Sequence[float],
    magnitude: Sequence[float],
    edges_hz: Sequence[float] = DEFAULT_BAND_EDGES_HZ,
) -> TonalBalance:
    """Convenience: band-sum a spectrum then normalize to a :class:`TonalBalance`."""
    return normalize_to_tonal_balance(band_energies(freqs, magnitude, edges_hz))
