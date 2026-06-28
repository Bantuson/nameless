"""FakeReferenceAnalyzer — deterministic, ML-free :class:`~nameless_workers.reference_ports.ReferenceAnalyzer`.

Produces a fully-formed :class:`ReferenceContext` derived *deterministically* from the input bytes
(seeded by their SHA-256), so the same reference always analyzes to the same context — exactly what
the orchestration / persistence / non-cloning tests need. It is composed the SAME way the real
analyzer is (an :class:`Embedder` for the style vector, a :class:`GenreTagger`, a
:class:`VibeDescriber`), with deterministic fakes as defaults — so a test against this fake exercises
the real control flow with only the heavy leaves swapped.

Crucially, it builds a :class:`NonMelodicFeatures` (which structurally cannot carry melody) and runs
:func:`assert_non_melodic` on its own output before returning — the non-cloning invariant is part of
the contract, not an afterthought. No librosa, no CLAP, no LLM.
"""

from __future__ import annotations

import hashlib
from typing import Optional
from uuid import UUID

import numpy as np

from ..domain.models import Embedding
from ..domain.reference import NonMelodicFeatures, ReferenceContext
from ..ports import Embedder
from ..pure.non_melodic import assert_non_melodic
from ..pure.tonal_balance import normalize_to_tonal_balance
from ..reference_ports import GenreTagger, VibeDescriber
from .embed_fake import FakeEmbedder
from .genre_tagger import FakeGenreTagger
from .vibe_describer_fake import FakeVibeDescriber

FAKE_REF_ANALYZER_VERSION = "fake-ref-analyzer-0"


class FakeReferenceAnalyzer:
    """A deterministic stand-in for the real restricted reference analyzer."""

    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        genre_tagger: Optional[GenreTagger] = None,
        vibe_describer: Optional[VibeDescriber] = None,
    ) -> None:
        self._embedder = embedder or FakeEmbedder()
        self._genre_tagger = genre_tagger or FakeGenreTagger()
        self._vibe = vibe_describer or FakeVibeDescriber()

    def analyze(self, audio: bytes, reference_track_id: UUID) -> ReferenceContext:
        seed = int.from_bytes(hashlib.sha256(audio).digest()[:8], "big")
        rng = np.random.default_rng(seed)

        # --- style embedding (REUSES the embedder; a vibe vector, NOT melody) ---
        style_embedding: Embedding = self._embedder.embed_audio(audio)

        # --- coarse genre via the (pluggable) zero-shot tagger ---
        genre = self._genre_tagger.tag(style_embedding).top

        # --- non-melodic measured targets, all deterministic + musically sane ---
        # Tonal balance: a seeded 5-band shape, normalized to ratios summing to 1.
        raw_bands = rng.uniform(0.05, 1.0, size=5)
        tonal_balance = normalize_to_tonal_balance(raw_bands.tolist())
        stereo_width = round(float(rng.uniform(0.0, 0.8)), 3)
        lufs = round(float(-14.0 + (seed % 8)), 2)  # [-14, -6] LUFS — a sane master range
        tempo_centre = float(80 + (seed % 70))  # [80, 150) BPM
        tempo_bpm_min = round(tempo_centre - 3.0, 1)
        tempo_bpm_max = round(tempo_centre + 3.0, 1)
        duration_s = round(float(120 + (seed % 120)), 2)  # [120, 240) s — a full track

        features = NonMelodicFeatures(
            tonal_balance=tonal_balance,
            stereo_width=stereo_width,
            lufs=lufs,
            tempo_bpm_min=tempo_bpm_min,
            tempo_bpm_max=tempo_bpm_max,
            genre=genre,
            sample_rate=44_100,
            duration_s=duration_s,
        )

        # --- vibe prose from the MEASURED features only ---
        vibe_description = self._vibe.describe(features)

        context = ReferenceContext(
            reference_track_id=reference_track_id,
            style_embedding=style_embedding,
            non_melodic=features,
            vibe_description=vibe_description,
            analyzer_version=FAKE_REF_ANALYZER_VERSION,
        )
        # Belt to the structural suspenders: prove the output carries no melodic field.
        assert_non_melodic(context)
        return context
