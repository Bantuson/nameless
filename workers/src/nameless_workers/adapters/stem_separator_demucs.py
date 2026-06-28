"""DemucsStemSeparator — the REAL :class:`~nameless_workers.separation_ports.StemSeparator`.

Stem separation made concrete (SAMP-01). It runs Demucs over a track's raw audio and returns the
named stems + the separator provenance.

  * ``htdemucs_ft`` (default) — the four-stem set (vocals / drums / bass / other), fine-tuned, best
    overall quality. Demucs is **maintenance-only** (STACK.md §4) but remains the pragmatic default.
  * ``htdemucs_6s`` (opt-in)  — additionally isolates **piano + guitar**, directly useful for the
    project's alt-piano sampling. (Its piano stem has known artifacts — PITFALLS.md — so it is
    opt-in, not the default.)

The model is kept behind this port so the anticipated BS-RoFormer swap (``audio-separator``, STACK.md
§4) is a config change, never a call-site change.

WHY LAZY (and NOT run here): ``demucs`` / ``torch`` / ``torchaudio`` are GPU-wanted and would OOM the
4 GB build box. Importing this module is free; the heavy imports happen inside :meth:`separate`. The
pure content-hashing + record construction this feeds (``pure/separation.py``) is fully tested with
the deterministic fake. The exact env-gated command to run the real path is in workers/README.md.

KNOWN ARTIFACTS (PITFALLS.md — handle, don't trust blindly): Demucs per-stem auto-rescale breaks
relative stem volume; expect hi-hat/cymbal bleed into vocals and vocal-reverb left in "other" on
dense mixes. We re-encode each stem at the model's native sample rate and do NOT re-normalize across
stems (so relative levels are preserved for a faithful sample).
"""

from __future__ import annotations

import io

from ..domain.separation import (
    HTDEMUCS_4,
    HTDEMUCS_6,
    SeparatedStem,
    SeparationResult,
    StemType,
)

# Demucs version we pin against (STACK.md). Recorded as separation provenance on every stem.
DEMUCS_VERSION = "4.0.1"

# Which StemType set each supported model emits (in Demucs source order).
_MODEL_STEMS: dict[str, tuple[StemType, ...]] = {
    "htdemucs": HTDEMUCS_4,
    "htdemucs_ft": HTDEMUCS_4,
    "htdemucs_6s": HTDEMUCS_6,
}


class DemucsStemSeparator:
    """Real Demucs stem separation. Heavy imports are lazy; this is NOT run on the build box."""

    def __init__(self, model: str = "htdemucs_ft", *, version: str = DEMUCS_VERSION) -> None:
        if model not in _MODEL_STEMS:
            raise ValueError(
                f"unsupported Demucs model {model!r}; expected one of {sorted(_MODEL_STEMS)}"
            )
        self._model = model
        self._version = version

    @property
    def expected_stem_types(self) -> tuple[StemType, ...]:
        """The stem types this model emits (e.g. 6 for ``htdemucs_6s``) — used by callers/tests."""
        return _MODEL_STEMS[self._model]

    def separate(self, audio: bytes) -> SeparationResult:
        # ---- lazy heavy imports (env-gated; never imported on the light base install) ----
        import numpy as np  # noqa: F401  (used for stem array handling)
        import soundfile as sf
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model

        model = get_model(self._model)
        model.eval()

        # Decode the uploaded track to a float32 waveform at the model's sample rate.
        data, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        wav = torch.from_numpy(data.T)  # (channels, samples)
        if wav.shape[0] == 1:  # demucs expects stereo; duplicate mono → 2 channels
            wav = wav.repeat(2, 1)
        target_sr = model.samplerate
        if sr != target_sr:
            import torchaudio  # lazy; I/O glue only (STACK.md treats torchaudio as I/O, not strategic)

            wav = torchaudio.functional.resample(wav, sr, target_sr)

        # apply_model returns (sources, channels, samples); sources are in `model.sources` order.
        with torch.no_grad():
            sources = apply_model(model, wav[None], split=True, overlap=0.25)[0]

        order = list(model.sources)  # e.g. ['drums','bass','other','vocals'] (+piano,guitar for 6s)
        stems: list[SeparatedStem] = []
        for name, tensor in zip(order, sources):
            stem_type = StemType.from_db_str(name)
            # Encode the stem to WAV bytes at the native sample rate; relative level preserved
            # (NO cross-stem re-normalization — see the artifacts note above).
            buf = io.BytesIO()
            sf.write(buf, tensor.T.cpu().numpy(), target_sr, format="WAV")
            stems.append(SeparatedStem(stem_type=stem_type, audio=buf.getvalue()))

        # Return stems in the canonical StemType order for stable downstream records.
        canonical = self.expected_stem_types
        stems.sort(key=lambda s: canonical.index(s.stem_type))
        return SeparationResult(
            separator_model=self._model,
            separator_version=self._version,
            stems=stems,
            sample_rate=int(target_sr),
        )
