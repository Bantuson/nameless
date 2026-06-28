"""ClaudeVibeDescriber — the REAL :class:`~nameless_workers.reference_ports.VibeDescriber` (env-gated).

Turns the MEASURED non-melodic features into mood/space/era/texture/energy prose via Claude. The
output is human-facing interpretation, kept at a different trust level than the measured targets
(PITFALLS.md Pitfall 5) — never fed back as a machine conditioning target.

NON-CLONING AT THE PROMPT: the model is handed ONLY the non-melodic features (tempo band, loudness,
width, tonal tilt, coarse genre) — never f0/chroma/key/chords — and is instructed not to invent any.
It cannot narrate a tune it was never shown.

WHY LAZY: the ``anthropic`` SDK + a network call are env-gated (needs ``ANTHROPIC_API_KEY``); the test
suite uses :class:`FakeVibeDescriber`. The import happens inside :meth:`describe`, so importing this
module is free. Model + API shape per the project's Claude API reference (claude-opus-4-8, adaptive
thinking, ``effort: "low"`` for this short scoped task).
"""

from __future__ import annotations

import json

from ..domain.reference import NonMelodicFeatures

DEFAULT_MODEL = "claude-opus-4-8"
MODEL_VERSION = "claude-opus-4-8:vibe-1"


class VibeDescriptionError(RuntimeError):
    """Raised when the model produces no usable vibe text (safety refusal or empty content).

    A loud failure is deliberate: the job queue should retry / dead-letter rather than persist an
    empty ``vibe_description``, which would be a silent quality degradation (PITFALLS.md Pitfall 5).
    """

_SYSTEM = (
    "You are a music A&R assistant. Given ONLY measured, non-melodic descriptors of a finished "
    "track (tempo range, loudness, stereo width, coarse spectral balance, and a coarse genre tag), "
    "write a 1-2 sentence vibe description covering mood, space, era, texture, and energy. "
    "Hard rules: describe atmosphere and feel only. Do NOT invent or mention melody, key, chords, "
    "notes, lyrics, song structure, or any specific musical phrase — you were not given them and "
    "must not guess. Output the description only, no preamble."
)


class ClaudeVibeDescriber:
    """Real Claude-backed vibe description for a reference's non-melodic features."""

    def __init__(self, *, model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = None  # built lazily

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # lazy: SDK + network, env-gated via ANTHROPIC_API_KEY

            self._client = anthropic.Anthropic()
        return self._client

    @staticmethod
    def _features_payload(features: NonMelodicFeatures) -> str:
        """Compact, NON-melodic descriptor block handed to the model (no melody fields exist here)."""
        return json.dumps(
            {
                "tempo_bpm_range": [features.tempo_bpm_min, features.tempo_bpm_max],
                "lufs": features.lufs,
                "stereo_width": features.stereo_width,
                "tonal_balance_low_to_high": features.tonal_balance.bands(),
                "genre_hint": features.genre,
            }
        )

    def describe(self, features: NonMelodicFeatures) -> str:
        client = self._ensure_client()
        # claude-opus-4-8: adaptive thinking; effort "low" for this short, scoped generation.
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Measured non-melodic descriptors for this reference track:\n"
                        f"{self._features_payload(features)}\n\n"
                        "Write the vibe description."
                    ),
                }
            ],
        )
        # A safety refusal yields stop_reason == "refusal" with empty/altered content; treat it as a
        # hard failure so the job retries / dead-letters instead of persisting "".
        if getattr(response, "stop_reason", None) == "refusal":
            raise VibeDescriptionError(
                "Claude refused the vibe-description request (stop_reason='refusal'); "
                "refusing to persist an empty description."
            )
        # Concatenate the text blocks (skip any thinking blocks); strip to a single clean line.
        parts = [block.text for block in response.content if block.type == "text"]
        text = " ".join(p.strip() for p in parts if p.strip()).strip()
        # Empty content (refusal without the flag, thinking-only output, truncation) must also fail
        # loudly — never return "" to be silently persisted as the vibe.
        if not text:
            raise VibeDescriptionError(
                "Claude returned no usable vibe text "
                f"(stop_reason={getattr(response, 'stop_reason', None)!r}); refusing to persist an "
                "empty description."
            )
        return text
