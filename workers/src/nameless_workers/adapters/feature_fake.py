"""FakeFeatureExtractor — deterministic, ML-free :class:`~nameless_workers.ports.FeatureExtractor`.

Returns a fully-formed :class:`AudioFeatures` derived *deterministically* from the input bytes (seeded
by their SHA-256), so the same bytes always yield the same features — exactly what the orchestration
and persistence tests need. It produces a real 12-d chroma and runs the REAL Krumhansl-Schmuckler
estimator on it (so the fake's ``key`` is self-consistent with the pure function under test), plus
plausible tempo / onsets / beat-grid / LUFS in musically sane ranges. No librosa, no torch.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ..domain.models import AudioFeatures, F0Contour
from ..pure.key import estimate_key

FAKE_ANALYZER_VERSION = "fake-extractor-0"


class FakeFeatureExtractor:
    """A deterministic stand-in for the real librosa/torchcrepe/pyloudnorm extractor."""

    def __init__(self, sample_rate: int = 44_100, hop_length: int = 512) -> None:
        self._sr = sample_rate
        self._hop = hop_length

    def extract(self, audio: bytes) -> AudioFeatures:
        # Seed a private RNG from the content hash → deterministic per distinct input.
        seed = int.from_bytes(hashlib.sha256(audio).digest()[:8], "big")
        rng = np.random.default_rng(seed)

        frames = 64  # a small but non-trivial number of analysis frames
        # A chroma matrix biased toward one tonal centre so key estimation is meaningful, not noise.
        tonic = int(seed % 12)
        base = np.full(12, 0.15)
        # Emphasize a rough major triad relative to the chosen tonic (root, third, fifth).
        for degree in (0, 4, 7):
            base[(tonic + degree) % 12] += 0.6
        chroma = np.clip(
            base[:, None] + rng.normal(0.0, 0.05, size=(12, frames)),
            0.0,
            None,
        )
        chroma_mean = chroma.mean(axis=1)
        key = estimate_key(chroma_mean.tolist())

        # Plausible tempo in [70, 160) BPM and a matching beat grid.
        tempo_bpm = float(70 + (seed % 90))
        beat_period = 60.0 / tempo_bpm
        n_beats = 8
        beat_grid = [round(i * beat_period, 4) for i in range(n_beats)]
        # Onsets near the beats with small deterministic jitter.
        onsets = [round(b + float(rng.uniform(-0.01, 0.01)), 4) for b in beat_grid]

        duration_s = round(n_beats * beat_period, 4)
        # f0 contour: a slowly varying pitch around a seed-derived centre (Hz), 10ms hop.
        n_f0 = int(duration_s / 0.01)
        centre_hz = 110.0 * (2 ** ((tonic) / 12.0))  # A2-ish, transposed by the tonic
        f0_times = [round(i * 0.01, 4) for i in range(n_f0)]
        f0_hz = [round(centre_hz * (1.0 + 0.02 * float(np.sin(i / 8.0))), 3) for i in range(n_f0)]
        f0_conf = [round(0.85 + 0.1 * float(rng.uniform(0, 1)), 3) for _ in range(n_f0)]

        loudness_lufs = round(-20.0 + (seed % 12), 2)  # [-20, -8] LUFS — sane fragment range

        return AudioFeatures(
            f0_contour=F0Contour(times_s=f0_times, f0_hz=f0_hz, confidence=f0_conf),
            chroma=chroma.round(5).tolist(),
            chroma_mean=chroma_mean.round(5).tolist(),
            onsets_s=onsets,
            beat_grid_s=beat_grid,
            tempo_bpm=tempo_bpm,
            key=key,
            loudness_lufs=loudness_lufs,
            sample_rate=self._sr,
            duration_s=duration_s,
            hop_length=self._hop,
            analyzer_version=FAKE_ANALYZER_VERSION,
        )
