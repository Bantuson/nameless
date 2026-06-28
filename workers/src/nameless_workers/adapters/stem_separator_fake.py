"""FakeStemSeparator — deterministic, ML-free :class:`~nameless_workers.separation_ports.StemSeparator`.

Produces a full :class:`SeparationResult` derived *deterministically* from the input bytes (seeded by
their SHA-256), so the same track always separates to the same stems — exactly what the orchestration
/ retention / idempotency tests need. Each stem's bytes are distinct per (input, stem_type), so their
content hashes differ (a real separation never yields identical stems). No demucs, no torch.

Defaults to the four-stem htdemucs set; pass ``stem_types=HTDEMUCS_6`` (and a matching ``model``) to
exercise the piano/guitar path that ``htdemucs_6s`` adds.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

from ..domain.separation import (
    HTDEMUCS_4,
    SeparatedStem,
    SeparationResult,
    StemType,
)

FAKE_SEPARATOR_MODEL = "fake-demucs"
FAKE_SEPARATOR_VERSION = "0"


class FakeStemSeparator:
    """A deterministic stand-in for the real Demucs separator."""

    def __init__(
        self,
        stem_types: Sequence[StemType] = HTDEMUCS_4,
        *,
        model: str = FAKE_SEPARATOR_MODEL,
        version: str = FAKE_SEPARATOR_VERSION,
        sample_rate: int = 44_100,
    ) -> None:
        self._stem_types = list(stem_types)
        self._model = model
        self._version = version
        self._sample_rate = sample_rate

    def separate(self, audio: bytes) -> SeparationResult:
        stems: list[SeparatedStem] = []
        for stem_type in self._stem_types:
            # Distinct, deterministic bytes per (stem_type, input) → distinct content hashes.
            digest = hashlib.sha256(
                b"stem:" + stem_type.value.encode("utf-8") + b":" + audio
            ).digest()
            # Repeat the digest a few times so a "stem" is a small but non-trivial blob.
            data = digest * 8
            stems.append(SeparatedStem(stem_type=stem_type, audio=data))
        return SeparationResult(
            separator_model=self._model,
            separator_version=self._version,
            stems=stems,
            sample_rate=self._sample_rate,
        )
