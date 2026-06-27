"""Krumhansl-Schmuckler key estimation — pure function over a 12-d chroma vector.

THE INTUITION (full math in workers/LEARNING.md). A chromagram tells you how much energy sits in each
of the 12 pitch classes (C, C#, …, B), folding away octave. Average it over time and you get a 12-d
"how much was each note used" profile for the fragment. Krumhansl & Schmuckler measured, with human
listeners, how strongly each scale degree implies a given key — the result is two 12-d *key profiles*
(one major, one minor). To name the key you slide each profile to every one of the 12 tonics and ask:
"which rotated profile best correlates with what I actually heard?" The best of the 24
(12 tonics × {major, minor}) is the estimated key, and the correlation itself is a confidence — a low
winner means genuinely ambiguous tonality (atonal, percussive, a single sustained note), which is
honest signal, not a bug.

This is a pure function: a 12-vector in, a :class:`KeyEstimate` out. No librosa, no audio, no global
state — so it is trivially and exhaustively testable (a synthetic C-major profile must resolve to
``C:maj``; transposing the input up a semitone must transpose the answer to ``C#:maj``; etc.).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from ..domain.models import KeyEstimate

# The Krumhansl-Kessler probe-tone profiles, indexed by scale degree (index 0 = the tonic).
# These are the canonical published weights (Krumhansl, "Cognitive Foundations of Musical Pitch",
# 1990). They are tonic-relative: to score a key whose tonic is pitch-class ``t``, the weight for an
# observed pitch-class ``pc`` is ``PROFILE[(pc - t) % 12]``.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)

# Pitch-class names (sharps). Index 0 = C, matching librosa's chroma convention.
_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation coefficient between two 12-vectors.

    Returns 0.0 if either input has zero variance (a flat chroma — e.g. silence or perfectly uniform
    energy — has no tonal centre to correlate, so every key is equally (un)likely).
    """
    xc = x - x.mean()
    yc = y - y.mean()
    denom = float(np.sqrt(np.dot(xc, xc) * np.dot(yc, yc)))
    if denom == 0.0:
        return 0.0
    return float(np.dot(xc, yc) / denom)


def estimate_key(chroma_mean: Sequence[float]) -> KeyEstimate:
    """Estimate the musical key from a 12-d (time-averaged) chroma vector.

    Tries all 24 candidate keys (12 tonics × major/minor), correlating the chroma against each
    tonic-rotated K-S profile, and returns the best as a :class:`KeyEstimate` whose ``correlation`` is
    the winning Pearson r (the confidence). Deterministic and pure.

    Raises ``ValueError`` if ``chroma_mean`` is not length 12.
    """
    chroma = np.asarray(chroma_mean, dtype=np.float64)
    if chroma.shape != (12,):
        raise ValueError(f"chroma_mean must be a length-12 vector, got shape {chroma.shape}")

    best_corr = -2.0  # below the −1 floor of a real correlation, so any real key wins
    best_tonic = 0
    best_mode = "maj"

    for tonic in range(12):
        # Rotate the tonic-relative profile so degree 0 lands on pitch class `tonic`.
        # profile_for_key[pc] = PROFILE[(pc - tonic) % 12]
        rotation = (np.arange(12) - tonic) % 12
        major_rot = _MAJOR_PROFILE[rotation]
        minor_rot = _MINOR_PROFILE[rotation]

        corr_major = _pearson(chroma, major_rot)
        if corr_major > best_corr:
            best_corr, best_tonic, best_mode = corr_major, tonic, "maj"

        corr_minor = _pearson(chroma, minor_rot)
        if corr_minor > best_corr:
            best_corr, best_tonic, best_mode = corr_minor, tonic, "min"

    name = f"{_PITCH_NAMES[best_tonic]}:{best_mode}"
    return KeyEstimate(
        tonic_pc=best_tonic,
        mode=best_mode,  # type: ignore[arg-type]  (constrained to maj|min by construction)
        name=name,
        correlation=best_corr,
    )
