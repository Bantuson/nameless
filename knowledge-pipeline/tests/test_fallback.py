"""fallback_decision tests (KNOW-03) — the captions -> ASR -> reject ladder."""

from __future__ import annotations

from knowledge_pipeline.domain.models import (
    CaptionAvailability,
    CaptionSource,
    FallbackAction,
)
from knowledge_pipeline.pure.fallback import fallback_decision


def test_manual_captions_always_used_no_asr():
    d = fallback_decision(CaptionAvailability(has_manual=True, has_auto=True, auto_quality=0.1))
    assert d.action is FallbackAction.USE_CAPTIONS
    assert d.caption_source is CaptionSource.MANUAL


def test_good_auto_captions_used_as_is():
    d = fallback_decision(
        CaptionAvailability(has_manual=False, has_auto=True, auto_quality=0.8),
        auto_quality_floor=0.5,
    )
    assert d.action is FallbackAction.USE_CAPTIONS
    assert d.caption_source is CaptionSource.AUTO


def test_noisy_auto_captions_trigger_asr_when_enabled():
    d = fallback_decision(
        CaptionAvailability(has_manual=False, has_auto=True, auto_quality=0.2),
        asr_enabled=True,
        auto_quality_floor=0.5,
    )
    assert d.action is FallbackAction.FETCH_AND_ASR


def test_noisy_auto_falls_back_to_auto_when_asr_disabled():
    d = fallback_decision(
        CaptionAvailability(has_manual=False, has_auto=True, auto_quality=0.2),
        asr_enabled=False,
        auto_quality_floor=0.5,
    )
    assert d.action is FallbackAction.USE_CAPTIONS
    assert d.caption_source is CaptionSource.AUTO


def test_no_captions_triggers_asr_when_enabled():
    d = fallback_decision(CaptionAvailability(has_manual=False, has_auto=False), asr_enabled=True)
    assert d.action is FallbackAction.FETCH_AND_ASR


def test_no_captions_and_no_asr_rejects():
    d = fallback_decision(CaptionAvailability(has_manual=False, has_auto=False), asr_enabled=False)
    assert d.action is FallbackAction.REJECT


def test_auto_with_unknown_quality_treated_as_below_floor():
    # auto present but no quality proxy ⇒ defaults to 0.0 ⇒ below floor ⇒ prefer ASR.
    d = fallback_decision(
        CaptionAvailability(has_manual=False, has_auto=True, auto_quality=None),
        asr_enabled=True,
    )
    assert d.action is FallbackAction.FETCH_AND_ASR
