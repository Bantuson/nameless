"""Stereo width — mid/side energy + L/R correlation. Pure functions, no librosa, no I/O.

Stereo width is a *spatial* descriptor: how much of a track's energy lives in the stereo difference
(the "side") versus the mono sum (the "mid"). It is non-melodic by nature — it says nothing about
which notes play, only how wide the image is — so it is a safe conditioning/mix target
(ARCHITECTURE.md Pattern 2; STACK.md "stereo width via mid/side energy ratio + L/R correlation").

LEARNING — the mid/side (M/S) transform:
    mid  = (L + R) / 2      # what a mono fold-down hears
    side = (L - R) / 2      # everything that differs between the channels
A fully mono signal has ``L == R`` so ``side == 0`` → width 0. A fully decorrelated equal-power L/R
pair has equal mid and side energy → width **~0.5** (NOT 1.0); the metric only reaches 1.0 for a true
anti-phase signal (``R = -L``), where all energy is in the side. We report width as
``side_energy / (mid_energy + side_energy)`` ∈ [0,1] (scale-invariant): 0 = mono, ~0.5 = fully
decorrelated, →1 = anti-phase. L/R correlation is the Pearson correlation of the two channels:
+1 = identical (mono), 0 = independent, −1 = anti-phase — a second, complementary view of width.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def mid_side(left: Sequence[float], right: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """Return the (mid, side) signals from L/R channels. ``mid=(L+R)/2``, ``side=(L-R)/2``."""
    l = np.asarray(left, dtype=np.float64)
    r = np.asarray(right, dtype=np.float64)
    if l.shape != r.shape:
        raise ValueError(f"left and right must match: {l.shape} vs {r.shape}")
    return (l + r) / 2.0, (l - r) / 2.0


def _energy(x: np.ndarray) -> float:
    """Sum of squares (signal energy)."""
    return float(np.sum(x.astype(np.float64) ** 2))


def stereo_width_ratio(left: Sequence[float], right: Sequence[float]) -> float:
    """Stereo width in [0, 1] = ``side_energy / (mid_energy + side_energy)``.

    Mono (``L == R``) → 0. Silence (both channels zero) → 0 (no image to measure). Fully
    decorrelated equal-power L/R → ~0.5; only true anti-phase (``R = -L``) reaches 1.0.
    """
    mid, side = mid_side(left, right)
    me, se = _energy(mid), _energy(side)
    denom = me + se
    if denom == 0.0:
        return 0.0
    return se / denom


def lr_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Pearson correlation between L and R in [−1, 1]. A constant/silent channel → 0 (undefined)."""
    l = np.asarray(left, dtype=np.float64)
    r = np.asarray(right, dtype=np.float64)
    if l.shape != r.shape:
        raise ValueError(f"left and right must match: {l.shape} vs {r.shape}")
    if l.size < 2:
        return 0.0
    ls, rs = l.std(), r.std()
    if ls == 0.0 or rs == 0.0:
        return 0.0
    return float(np.corrcoef(l, r)[0, 1])


def stereo_width_from_mono(signal: Sequence[float]) -> float:
    """A single-channel (mono) signal has zero width by definition — convenience for mono inputs."""
    _ = np.asarray(signal, dtype=np.float64)
    return 0.0
