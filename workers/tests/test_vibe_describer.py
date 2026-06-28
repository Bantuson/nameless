"""Fake vibe describer — deterministic, grounded in numbers, and never melodic."""

from __future__ import annotations

import pytest

from nameless_workers.adapters.vibe_describer_claude import (
    ClaudeVibeDescriber,
    VibeDescriptionError,
)
from nameless_workers.adapters.vibe_describer_fake import FakeVibeDescriber
from nameless_workers.domain.reference import NonMelodicFeatures, TonalBalance


def _features(*, tempo: float, lufs: float, width: float, low: float, high: float) -> NonMelodicFeatures:
    # Spread the remaining energy across the middle bands; only low/high tilt matters for the test.
    mid_each = max(0.0, (1.0 - low - high) / 3.0)
    return NonMelodicFeatures(
        tonal_balance=TonalBalance(low=low, low_mid=mid_each, mid=mid_each, high_mid=mid_each, high=high),
        stereo_width=width,
        lufs=lufs,
        tempo_bpm_min=tempo - 2,
        tempo_bpm_max=tempo + 2,
        genre="amapiano",
        sample_rate=44_100,
        duration_s=180.0,
    )


def test_deterministic_for_the_same_features():
    d = FakeVibeDescriber()
    f = _features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1)
    assert d.describe(f) == d.describe(f)


def test_mentions_no_melodic_terms():
    d = FakeVibeDescriber()
    text = d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1)).lower()
    for forbidden in ("melody", "chord", "key", "note", "pitch", "scale"):
        assert forbidden not in text, f"vibe prose must not mention {forbidden!r}: {text!r}"


def test_tempo_drives_energy_word():
    d = FakeVibeDescriber()
    fast = d.describe(_features(tempo=128, lufs=-9, width=0.5, low=0.3, high=0.2))
    slow = d.describe(_features(tempo=70, lufs=-12, width=0.2, low=0.3, high=0.2))
    assert "driving" in fast
    assert "slow" in slow


def test_tonal_tilt_drives_the_balance_phrase():
    d = FakeVibeDescriber()
    warm = d.describe(_features(tempo=110, lufs=-9, width=0.5, low=0.6, high=0.05))
    bright = d.describe(_features(tempo=110, lufs=-9, width=0.5, low=0.05, high=0.6))
    assert "bass-forward" in warm
    assert "airy" in bright


# --- ClaudeVibeDescriber refusal / empty-response handling (WR-03) -------------------------------
# These exercise the REAL describer's response handling without any network or the anthropic SDK, by
# injecting a fake client into the lazily-built _client slot.


class _Block:
    def __init__(self, type: str, text: str = "") -> None:
        self.type = type
        self.text = text


class _Response:
    def __init__(self, *, stop_reason: str, content: list[_Block]) -> None:
        self.stop_reason = stop_reason
        self.content = content


class _FakeMessages:
    def __init__(self, response: _Response) -> None:
        self._response = response

    def create(self, **_kwargs) -> _Response:
        return self._response


class _FakeClient:
    def __init__(self, response: _Response) -> None:
        self.messages = _FakeMessages(response)


def _claude_with(response: _Response) -> ClaudeVibeDescriber:
    d = ClaudeVibeDescriber()
    d._client = _FakeClient(response)  # inject — skips _ensure_client / anthropic import
    return d


def test_claude_raises_on_safety_refusal():
    d = _claude_with(_Response(stop_reason="refusal", content=[]))
    with pytest.raises(VibeDescriptionError):
        d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1))


def test_claude_raises_on_empty_text_content():
    # No refusal flag, but only thinking blocks / no usable text — must still fail loudly, not "".
    d = _claude_with(_Response(stop_reason="end_turn", content=[_Block("thinking")]))
    with pytest.raises(VibeDescriptionError):
        d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1))


def test_claude_raises_on_whitespace_only_text():
    d = _claude_with(_Response(stop_reason="end_turn", content=[_Block("text", "   \n  ")]))
    with pytest.raises(VibeDescriptionError):
        d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1))


def test_claude_returns_clean_text_on_success():
    d = _claude_with(
        _Response(
            stop_reason="end_turn",
            content=[_Block("thinking"), _Block("text", "  late-night, wide and warm.  ")],
        )
    )
    assert d.describe(_features(tempo=112, lufs=-9, width=0.5, low=0.4, high=0.1)) == (
        "late-night, wide and warm."
    )
