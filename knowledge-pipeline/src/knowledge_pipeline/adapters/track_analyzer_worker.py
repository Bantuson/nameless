"""WorkerTrackAnalyzer — the REAL :class:`~knowledge_pipeline.ports.TrackAnalyzer` (KNOW-10, env-gated).

REUSES the Phase-2 ``workers`` audio plane rather than re-implementing DSP (CONTEXT: "do NOT re-implement
DSP"): it runs the SAME ``LibrosaFeatureExtractor`` (tempo/key/onsets/beat-grid/LUFS via librosa +
torchcrepe + pyloudnorm) and ``ClapEmbedder`` (LAION-CLAP) the fragment graph uses, computes the few extra
*non-melodic* signatures the grounding leg needs (swing off the beat grid, multiband tonal balance, mid/
side stereo width, coarse CLAP nearest-tags), and maps everything through the PURE
:func:`~knowledge_pipeline.pure.audio_claims.features_to_record`. The DTO mapping is therefore tested with
canned numbers; this adapter only has to produce the primitives.

WHY EVERYTHING HEAVY IS LAZY (inside :meth:`analyze`): the 4GB build box cannot install torch/librosa/CLAP,
``nameless_workers`` is a SEPARATE package (installed only in the real worker env), and the whole test
suite runs against :class:`~knowledge_pipeline.adapters.track_analyzer_fake.FakeTrackAnalyzer`. Importing
this module must stay free — so ``nameless_workers``, ``librosa``, ``soundfile``, ``numpy`` are imported
only when :meth:`analyze` actually runs (the env-gated path).

CLONING-BOUNDARY NOTE (PITFALLS #6): this adapter extracts only the aggregate non-melodic descriptors a
record holds. It deliberately does NOT compute or return an f0 contour / detailed chroma as a conditioning
target from these reference tracks — what we do not store, we cannot accidentally clone.

Env-gated run (the user, later):
    # both packages on the path, with the heavy extras:
    uv pip install -e workers[ml] -e knowledge-pipeline
    skills ground --tracks <dir-of-audio>          # (or wire WorkerTrackAnalyzer in a script)
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable, Optional, Sequence

from ..domain.grounding import AudioAnalysisRecord, ClapTag, TrackRef
from ..pure.audio_claims import features_to_record

# A small, fixed coarse-genre/vibe vocabulary for CLAP zero-shot nearest-tag. COARSE labels ONLY
# (PITFALLS #5: CLAP is weak for fine-grained genre) — used for a vibe signal, never a craft claim.
DEFAULT_CLAP_TAGS: tuple[str, ...] = (
    "amapiano",
    "deep house",
    "soulful piano",
    "jazz piano",
    "r&b",
    "afro house",
    "lo-fi",
    "ambient",
)


def _default_loader(track: TrackRef) -> bytes:
    """Load a track's audio bytes from a local file (``audio_uri`` as a path). Replace for an object store."""
    if not track.audio_uri:
        raise ValueError(f"track '{track.track_id}' has no audio_uri to load bytes from")
    with open(track.audio_uri, "rb") as fh:
        return fh.read()


class WorkerTrackAnalyzer:
    """Real released-track analysis, reusing the Phase-2 workers feature/CLAP adapters (env-gated)."""

    def __init__(
        self,
        *,
        load_bytes: Optional[Callable[[TrackRef], bytes]] = None,
        clap_tags: Sequence[str] = DEFAULT_CLAP_TAGS,
        device: str = "cpu",
        separator_model: Optional[str] = None,
        now: Optional[Callable[[], _dt.datetime]] = None,
    ) -> None:
        self._load_bytes = load_bytes or _default_loader
        self._clap_tags = tuple(clap_tags)
        self._device = device
        self._separator_model = separator_model
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))
        self._extractor = None  # lazy workers FeatureExtractor
        self._embedder = None   # lazy workers Embedder

    # ---- lazy workers adapters (the Phase-2 plane) ----
    def _ensure_workers(self):
        if self._extractor is None or self._embedder is None:
            # nameless_workers is a separate package, present only in the real worker env.
            from nameless_workers.adapters.embed_clap import ClapEmbedder
            from nameless_workers.adapters.feature_librosa import LibrosaFeatureExtractor

            self._extractor = LibrosaFeatureExtractor(device=self._device)
            self._embedder = ClapEmbedder(device=self._device)
        return self._extractor, self._embedder

    def analyze(self, track: TrackRef) -> AudioAnalysisRecord:
        import numpy as np  # lazy

        audio = self._load_bytes(track)
        extractor, embedder = self._ensure_workers()

        # 1) The shared Phase-2 features: tempo / key / beat-grid / onsets / LUFS.
        features = extractor.extract(audio)

        # 2) The extra non-melodic signatures the grounding leg needs (swing / tonal balance / width).
        y, sr = self._decode(audio)
        swing = self._swing(features.onsets_s, features.beat_grid_s)
        tonal = self._tonal_balance(y, sr)
        width = self._stereo_width(audio)

        # 3) Coarse CLAP nearest-tags (zero-shot): rank the fixed vocabulary by cosine to the audio vector.
        clap_tags = self._clap_nearest(embedder, audio)

        n = len(y) if hasattr(y, "__len__") else 0
        region_ms = (0, int(round((n / sr) * 1000)) if sr else 0)

        return features_to_record(
            track,
            tempo_bpm=float(features.tempo_bpm),
            swing_ratio=swing,
            key_name=features.key.name,
            key_confidence=float(features.key.correlation),
            tonal_balance=tonal,
            stereo_width=width,
            loudness_lufs=float(features.loudness_lufs),
            clap_tags=clap_tags,
            analyzer_version=f"worker:{features.analyzer_version}",
            embed_model=getattr(embedder, "MODEL_NAME", "laion_clap"),
            separator_model=self._separator_model,
            region_ms=region_ms,
            analyzed_at=self._now(),
        )

    # ---- DSP helpers (lazy; only the non-melodic surface) -------------------------------------
    @staticmethod
    def _decode(audio: bytes):
        """Decode bytes -> (mono float32, sr) (mirrors the workers extractor's decode path)."""
        import io

        import numpy as np
        import soundfile as sf

        try:
            data, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
        except Exception:
            import librosa  # lazy

            data, sr = librosa.load(io.BytesIO(audio), sr=None, mono=True)
        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 2:
            data = data.mean(axis=1)
        return data, int(sr)

    @staticmethod
    def _swing(onsets_s: list[float], beat_grid_s: list[float]) -> float:
        """Swing = mean absolute onset deviation off the straight half-beat grid, normalized to [0,1]. Pure."""
        import numpy as np

        if len(beat_grid_s) < 2 or not onsets_s:
            return 0.0
        period = float(np.median(np.diff(beat_grid_s)))
        if period <= 0:
            return 0.0
        # nearest 8th-note slot for each onset; deviation as a fraction of the 8th-note step.
        step = period / 2.0
        devs = []
        for t in onsets_s:
            nearest = round((t - beat_grid_s[0]) / step) * step + beat_grid_s[0]
            devs.append(abs(t - nearest) / step)
        return float(min(1.0, np.mean(devs))) if devs else 0.0

    @staticmethod
    def _tonal_balance(y, sr: int) -> dict[str, float]:
        """Fraction of spectral energy in low(<250Hz)/mid(250-4k)/high(>4k) bands. Pure (numpy)."""
        import numpy as np

        if sr <= 0 or len(y) == 0:
            return {"low": 0.0, "mid": 0.0, "high": 0.0}
        spectrum = np.abs(np.fft.rfft(y)) ** 2
        freqs = np.fft.rfftfreq(len(y), d=1.0 / sr)
        total = float(spectrum.sum()) or 1.0
        low = float(spectrum[freqs < 250].sum()) / total
        mid = float(spectrum[(freqs >= 250) & (freqs < 4000)].sum()) / total
        high = float(spectrum[freqs >= 4000].sum()) / total
        return {"low": round(low, 4), "mid": round(mid, 4), "high": round(high, 4)}

    @staticmethod
    def _stereo_width(audio: bytes) -> float:
        """Mid/side: side-energy fraction = S/(M+S) over L/R. 0 for mono. Pure (numpy)."""
        import io

        import numpy as np
        import soundfile as sf

        try:
            data, _sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        except Exception:
            return 0.0
        if data.ndim != 2 or data.shape[1] < 2:
            return 0.0
        left, right = data[:, 0], data[:, 1]
        mid = (left + right) / 2.0
        side = (left - right) / 2.0
        m_e = float(np.sum(mid ** 2))
        s_e = float(np.sum(side ** 2))
        denom = m_e + s_e
        return round(s_e / denom, 4) if denom > 0 else 0.0

    def _clap_nearest(self, embedder, audio: bytes) -> list[ClapTag]:
        """Rank the fixed coarse-tag vocabulary by cosine similarity to the track's CLAP audio vector."""
        import numpy as np

        a = np.asarray(embedder.embed_audio(audio).vector, dtype=np.float64)
        tags: list[ClapTag] = []
        for tag in self._clap_tags:
            t = np.asarray(embedder.embed_text(tag).vector, dtype=np.float64)
            denom = (np.linalg.norm(a) * np.linalg.norm(t)) or 1.0
            tags.append(ClapTag(tag=tag, score=round(float(a @ t) / float(denom), 4)))
        tags.sort(key=lambda c: -c.score)
        return tags
