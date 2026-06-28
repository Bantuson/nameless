"""RestrictedReferenceAnalyzer — the REAL :class:`~nameless_workers.reference_ports.ReferenceAnalyzer`.

The non-cloning path made concrete (REF-02 / REF-03). It computes, from a reference's raw audio,
ONLY non-melodic descriptors:
  * CLAP **style** embedding   — reuses the Phase-2 :class:`~nameless_workers.ports.Embedder` (audio
                                 tower over the whole track) — a global vibe vector, NOT a melody
  * tonal balance              — ``librosa`` STFT magnitude → 5-band ratios (``pure/tonal_balance.py``)
  * stereo width               — mid/side energy on the decoded L/R (``pure/stereo_width.py``)
  * LUFS                       — ``pyloudnorm`` integrated loudness (ITU-R BS.1770-4)
  * tempo RANGE                — ``librosa.beat.beat_track`` centre ± a margin (rhythm, not melody)
  * coarse genre               — pluggable :class:`~nameless_workers.reference_ports.GenreTagger`
  * vibe prose                 — :class:`~nameless_workers.reference_ports.VibeDescriber` over the
                                 MEASURED features only

**It deliberately does NOT call ``librosa.feature.chroma_cqt`` or ``torchcrepe`` — there is no
chroma, no f0, no key estimation here.** That is the whole point: the reference's melodic content is
never materialized, so generation has nothing to clone from (contrast the Phase-2
``LibrosaFeatureExtractor``, which DOES compute those for the producer's OWN fragments). The output
type (:class:`NonMelodicFeatures`) structurally cannot hold a melody, and the analyzer runs
:func:`assert_non_melodic` on its result as a final tripwire.

WHY LAZY: ``librosa``/``soundfile``/``pyloudnorm`` (and the Embedder's CLAP) are env-gated; importing
this module is free. The math each step relies on is the pure functions in ``pure/`` (fully tested).
"""

from __future__ import annotations

import io
from typing import Optional
from uuid import UUID

import numpy as np

from ..domain.models import Embedding
from ..domain.reference import NonMelodicFeatures, ReferenceContext
from ..ports import Embedder
from ..pure.non_melodic import assert_non_melodic
from ..pure.stereo_width import stereo_width_ratio
from ..pure.tonal_balance import tonal_balance_from_spectrum
from ..reference_ports import GenreTagger, VibeDescriber

ANALYZER_VERSION = "librosa0.11-pyloudnorm0.1-clap1.1.7-restricted-v1"

STFT_N_FFT = 2048
STFT_HOP = 512
TEMPO_MARGIN_BPM = 4.0  # half-width of the reported tempo band around the estimate
VOICING_FLOOR_LUFS = -70.0


class RestrictedReferenceAnalyzer:
    """Real NON-melodic reference analysis. Reuses the CLAP Embedder; never computes f0/chroma."""

    def __init__(
        self,
        embedder: Embedder,
        genre_tagger: GenreTagger,
        vibe_describer: VibeDescriber,
    ) -> None:
        self._embedder = embedder
        self._genre_tagger = genre_tagger
        self._vibe = vibe_describer

    # ---- decode keeping channels (stereo width needs L/R) ----
    @staticmethod
    def _decode_stereo(audio: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        """Decode bytes → (mono, left, right, sr). Mono input → L == R (width will be 0)."""
        import soundfile as sf  # lazy

        try:
            data, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        except Exception:
            import os
            import tempfile

            import librosa  # lazy

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                    tmp.write(audio)
                    tmp_path = tmp.name
                mono, sr = librosa.load(tmp_path, sr=None, mono=True)
                data = np.column_stack([mono, mono])
            finally:
                if tmp_path is not None:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 1:
            data = data[:, np.newaxis]
        left = data[:, 0]
        right = data[:, 1] if data.shape[1] > 1 else data[:, 0]
        mono = data.mean(axis=1)
        return mono, left, right, int(sr)

    def analyze(self, audio: bytes, reference_track_id: UUID) -> ReferenceContext:
        import librosa  # lazy

        mono, left, right, sr = self._decode_stereo(audio)
        duration_s = float(len(mono) / sr) if sr else 0.0

        # ---- tonal balance: STFT magnitude (avg over frames) → 5-band ratios. NO chroma. ----
        stft = np.abs(librosa.stft(mono, n_fft=STFT_N_FFT, hop_length=STFT_HOP))
        avg_magnitude = stft.mean(axis=1)  # (1 + n_fft/2,)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=STFT_N_FFT)
        tonal_balance = tonal_balance_from_spectrum(freqs.tolist(), avg_magnitude.tolist())

        # ---- stereo width: mid/side energy on L/R ----
        stereo_width = round(stereo_width_ratio(left, right), 3)

        # ---- LUFS (pyloudnorm; pass stereo for a true reading) ----
        lufs = round(self._integrated_lufs(np.column_stack([left, right]), sr), 2)

        # ---- tempo RANGE (rhythm, not melody): beat_track centre ± margin ----
        tempo, _beats = librosa.beat.beat_track(y=mono, sr=sr, hop_length=STFT_HOP)
        tempo_centre = float(np.atleast_1d(tempo)[0])
        tempo_bpm_min = round(max(0.0, tempo_centre - TEMPO_MARGIN_BPM), 1)
        tempo_bpm_max = round(tempo_centre + TEMPO_MARGIN_BPM, 1)

        # ---- CLAP style embedding (REUSE the embedder over the raw bytes) ----
        style_embedding: Embedding = self._embedder.embed_audio(audio)

        # ---- coarse genre tag ----
        genre = self._genre_tagger.tag(style_embedding).top

        features = NonMelodicFeatures(
            tonal_balance=tonal_balance,
            stereo_width=stereo_width,
            lufs=lufs,
            tempo_bpm_min=tempo_bpm_min,
            tempo_bpm_max=tempo_bpm_max,
            genre=genre,
            sample_rate=sr,
            duration_s=round(duration_s, 2),
        )

        # ---- vibe prose from the MEASURED non-melodic features only ----
        vibe_description = self._vibe.describe(features)

        context = ReferenceContext(
            reference_track_id=reference_track_id,
            style_embedding=style_embedding,
            non_melodic=features,
            vibe_description=vibe_description,
            analyzer_version=ANALYZER_VERSION,
        )
        # Final tripwire: refuse to emit a context that somehow declares a melodic field.
        assert_non_melodic(context)
        return context

    @staticmethod
    def _integrated_lufs(samples: np.ndarray, sr: int) -> float:
        import pyloudnorm as pyln  # lazy

        if sr <= 0 or samples.size == 0:
            return VOICING_FLOOR_LUFS
        try:
            meter = pyln.Meter(sr)  # BS.1770-4 K-weighting + gating
            loudness = float(meter.integrated_loudness(samples))
        except Exception:
            return VOICING_FLOOR_LUFS
        if not np.isfinite(loudness):
            return VOICING_FLOOR_LUFS
        return loudness
