"""LibrosaFeatureExtractor — the REAL :class:`~nameless_workers.ports.FeatureExtractor` (CAP-03).

Computes, from raw audio bytes:
  * f0 contour            — ``torchcrepe`` (CREPE), the melody as a continuous pitch signal (PRD §8)
  * chromagram + key      — ``librosa.feature.chroma_cqt`` → Krumhansl-Schmuckler (pure ``estimate_key``)
  * onsets                — ``librosa.onset.onset_detect``
  * beat grid + tempo     — ``librosa.beat.beat_track``
  * loudness (LUFS)       — ``pyloudnorm`` integrated loudness (ITU-R BS.1770-4)

WHY THE HEAVY IMPORTS ARE LAZY (inside :meth:`extract`): the 4GB build box cannot install torch/
librosa, and the whole test suite runs against :class:`FakeFeatureExtractor`. Importing this module
must stay free, so ``librosa``/``soundfile``/``torch``/``torchcrepe``/``pyloudnorm`` are imported only
when :meth:`extract` actually runs (the env-gated path). The math/intuition for each step is in
workers/LEARNING.md.
"""

from __future__ import annotations

import io

import numpy as np

from ..domain.models import AudioFeatures, F0Contour
from ..pure.key import estimate_key

ANALYZER_VERSION = "librosa0.11-torchcrepe-pyloudnorm0.1-v1"

# Analysis params (documented so re-analysis under a different hop is detectable via analyzer_version).
HOP_LENGTH = 512          # frame hop for chroma/onset/beat (native sr)
CREPE_SR = 16_000         # CREPE expects 16 kHz mono
CREPE_HOP = 160           # 160 / 16000 = 10 ms frames
CREPE_FMIN = 50.0         # musical pitch floor (Hz)
CREPE_FMAX = 1100.0       # musical pitch ceiling (Hz) — covers sung/hummed melody
VOICING_FLOOR_LUFS = -70.0  # what to record when a fragment is too short/quiet for a real LUFS read


class LibrosaFeatureExtractor:
    """Real DSP feature extraction. Stateless; one instance can analyze many fragments."""

    def __init__(self, *, crepe_model: str = "full", device: str = "cpu") -> None:
        self._crepe_model = crepe_model
        self._device = device

    # ---- decode ----------------------------------------------------------------------------
    @staticmethod
    def _decode(audio: bytes) -> tuple[np.ndarray, int]:
        """Decode bytes → (mono float32 samples, sample_rate). Tries libsndfile, falls back to librosa."""
        import soundfile as sf  # lazy

        try:
            data, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
        except Exception:
            # Compressed formats (mp3/m4a) that libsndfile may not read → temp file + librosa/audioread.
            import os
            import tempfile

            import librosa  # lazy

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                    tmp.write(audio)
                    tmp_path = tmp.name
                data, sr = librosa.load(tmp_path, sr=None, mono=True)
            finally:
                if tmp_path is not None:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 2:  # stereo → mono (mean of channels)
            data = data.mean(axis=1)
        return data, int(sr)

    # ---- the full feature set --------------------------------------------------------------
    def extract(self, audio: bytes) -> AudioFeatures:
        import librosa  # lazy

        y, sr = self._decode(audio)
        duration_s = float(len(y) / sr) if sr else 0.0

        # ---- chroma (CQT) + time-averaged 12-d profile ----
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)  # (12, T)
        chroma_mean = chroma.mean(axis=1)
        key = estimate_key(chroma_mean.tolist())

        # ---- onsets (event times, seconds) ----
        onsets_s = librosa.onset.onset_detect(
            y=y, sr=sr, hop_length=HOP_LENGTH, units="time"
        ).tolist()

        # ---- beat grid + tempo ----
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP_LENGTH)
        tempo_bpm = float(np.atleast_1d(tempo)[0])  # librosa 0.10+ may return an array
        beat_grid_s = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH).tolist()

        # ---- f0 contour (CREPE @ 16 kHz) ----
        f0 = self._f0_contour(y, sr)

        # ---- loudness (LUFS, BS.1770) ----
        loudness_lufs = self._integrated_lufs(y, sr)

        return AudioFeatures(
            f0_contour=f0,
            chroma=np.round(chroma, 5).tolist(),
            chroma_mean=np.round(chroma_mean, 5).tolist(),
            onsets_s=[round(float(t), 4) for t in onsets_s],
            beat_grid_s=[round(float(t), 4) for t in beat_grid_s],
            tempo_bpm=round(tempo_bpm, 3),
            key=key,
            loudness_lufs=round(loudness_lufs, 2),
            sample_rate=sr,
            duration_s=round(duration_s, 4),
            hop_length=HOP_LENGTH,
            analyzer_version=ANALYZER_VERSION,
        )

    # ---- f0 via torchcrepe ----
    def _f0_contour(self, y: np.ndarray, sr: int) -> F0Contour:
        import librosa  # lazy
        import torch  # lazy
        import torchcrepe  # lazy

        # CREPE wants 16 kHz mono float32 as a (1, N) tensor.
        y16 = librosa.resample(y, orig_sr=sr, target_sr=CREPE_SR) if sr != CREPE_SR else y
        audio_t = torch.tensor(y16, dtype=torch.float32).unsqueeze(0)

        pitch, periodicity = torchcrepe.predict(
            audio_t,
            CREPE_SR,
            hop_length=CREPE_HOP,
            fmin=CREPE_FMIN,
            fmax=CREPE_FMAX,
            model=self._crepe_model,
            return_periodicity=True,
            batch_size=512,
            device=self._device,
        )
        pitch_np = pitch.squeeze(0).cpu().numpy()
        conf_np = periodicity.squeeze(0).cpu().numpy()
        n = pitch_np.shape[0]
        times = (np.arange(n) * CREPE_HOP / CREPE_SR).round(4)

        return F0Contour(
            times_s=times.tolist(),
            f0_hz=np.round(pitch_np, 3).tolist(),
            confidence=np.round(conf_np, 4).tolist(),
        )

    # ---- integrated LUFS via pyloudnorm ----
    @staticmethod
    def _integrated_lufs(y: np.ndarray, sr: int) -> float:
        import pyloudnorm as pyln  # lazy

        if sr <= 0 or len(y) == 0:
            return VOICING_FLOOR_LUFS
        try:
            meter = pyln.Meter(sr)  # BS.1770-4 K-weighting + gating
            loudness = float(meter.integrated_loudness(y))
        except Exception:
            return VOICING_FLOOR_LUFS
        # Too-short/too-quiet fragments gate to -inf; record a finite silence floor instead.
        if not np.isfinite(loudness):
            return VOICING_FLOOR_LUFS
        return loudness
