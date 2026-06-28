"""FakeVibeDescriber — deterministic, LLM-free :class:`~nameless_workers.reference_ports.VibeDescriber`.

Produces a stable mood/space/era/texture/energy line from the MEASURED non-melodic features alone, so
analyzer tests run with no Claude call. It is deliberately grounded in the numbers it is given (tempo
band, loudness, width, tonal tilt) — never inventing a melody, key, or chord — which both keeps the
fake honest and demonstrates the non-cloning discipline the real describer must follow.
"""

from __future__ import annotations

from ..domain.reference import NonMelodicFeatures

FAKE_VIBE_VERSION = "fake-vibe-0"


class FakeVibeDescriber:
    """A deterministic stand-in for the real Claude vibe describer."""

    def describe(self, features: NonMelodicFeatures) -> str:
        tempo_mid = (features.tempo_bpm_min + features.tempo_bpm_max) / 2.0
        energy = "driving" if tempo_mid >= 120 else "laid-back" if tempo_mid >= 90 else "slow"
        space = "wide and spacious" if features.stereo_width >= 0.4 else "intimate and centred"
        loud = "loud, mastered-hot" if features.lufs >= -9.0 else "dynamic, headroom-y"
        bands = features.tonal_balance.bands()
        # Compare sub+low-mid energy to high-mid+high to describe the spectral tilt (no notes).
        low_weight = bands[0] + bands[1]
        high_weight = bands[3] + bands[4]
        tilt = (
            "warm and bass-forward"
            if low_weight > high_weight
            else "bright and airy"
            if high_weight > low_weight
            else "balanced"
        )
        genre = features.genre or "genre-fluid"
        return (
            f"{energy}, {space}; {tilt} tonal balance; {loud}. "
            f"reads {genre}; mood: late-night, atmospheric."
        )
