"""``fallback_decision`` — the pure rule for the captions -> ASR -> reject ladder (KNOW-03).

Given only what caption tracks exist (and a cheap quality proxy for auto-captions), decide one of:
  * USE_CAPTIONS    — captions are good enough; do NOT spend GPU on ASR.
  * FETCH_AND_ASR   — captions missing or auto-quality below the floor; pull audio + faster-whisper.
  * REJECT          — nothing usable and ASR is disabled/unavailable.

Why this is its own pure function: the policy "when is it worth re-transcribing?" is a real judgement
with real cost (PITFALLS: "Only re-transcribe high-extractability-value videos — Whisper is GPU cost").
Isolating it from the fetch I/O makes that policy testable exhaustively and tunable in one place.

Trust ladder (manual > asr > auto): manual captions win outright. Auto-captions are used only if their
cheap quality proxy clears the floor; otherwise — if we can — we prefer ASR over noisy auto, because
faster-whisper handles producer jargon and code-switching far better than YouTube auto-captions.
"""

from __future__ import annotations

from ..domain.models import (
    CaptionAvailability,
    CaptionSource,
    FallbackAction,
    FallbackDecision,
)


def fallback_decision(
    captions: CaptionAvailability,
    *,
    asr_enabled: bool = True,
    auto_quality_floor: float = 0.5,
) -> FallbackDecision:
    """Decide the fetch path for one video from its caption availability. Pure.

    Args:
        captions: what tracks exist + a cheap auto-caption quality proxy (``auto_quality`` in [0,1]).
        asr_enabled: whether the ASR fallback is available this run (the ``[asr]`` extra installed /
            a GPU budgeted). When False, we never return FETCH_AND_ASR.
        auto_quality_floor: minimum auto-caption proxy quality to use auto-captions as-is.

    Returns:
        A :class:`FallbackDecision` naming the action, the chosen caption source (if any), and a reason.
    """
    # 1. Manual captions — gold. Always prefer them; never spend ASR.
    if captions.has_manual:
        return FallbackDecision(
            action=FallbackAction.USE_CAPTIONS,
            caption_source=CaptionSource.MANUAL,
            reason="manual captions present (highest trust)",
        )

    # 2. Auto captions present — judge their cheap quality proxy.
    if captions.has_auto:
        quality = captions.auto_quality if captions.auto_quality is not None else 0.0
        if quality >= auto_quality_floor:
            return FallbackDecision(
                action=FallbackAction.USE_CAPTIONS,
                caption_source=CaptionSource.AUTO,
                reason=f"auto captions clear quality floor ({quality:.2f} >= {auto_quality_floor:.2f})",
            )
        # Auto present but noisy: prefer ASR if we can, else fall back to the noisy auto (best effort).
        if asr_enabled:
            return FallbackDecision(
                action=FallbackAction.FETCH_AND_ASR,
                reason=f"auto captions below floor ({quality:.2f} < {auto_quality_floor:.2f}); re-transcribe with ASR",
            )
        return FallbackDecision(
            action=FallbackAction.USE_CAPTIONS,
            caption_source=CaptionSource.AUTO,
            reason="auto captions below floor but ASR disabled; using noisy auto (flag downstream)",
        )

    # 3. No captions at all.
    if asr_enabled:
        return FallbackDecision(
            action=FallbackAction.FETCH_AND_ASR,
            reason="no captions; pull audio and transcribe with ASR",
        )
    return FallbackDecision(
        action=FallbackAction.REJECT,
        reason="no captions and ASR disabled; nothing teachable to ingest",
    )
