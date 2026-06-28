"""WR-03 — yt-dlp caption availability is derived from USABLE vtt tracks, not merely listed ones.

These exercise the pure dict logic of the real :class:`YoutubeTranscriptFetcher` (``_has_usable_vtt`` /
``_pick_track``) with the same shape yt-dlp returns. They need NO network and NO yt-dlp install (the
library import is lazy, inside ``_fetch_via_ytdlp`` only), so they run on the base env. The full live
fetch path remains env-gated.
"""

from __future__ import annotations

from knowledge_pipeline.adapters.fetch_youtube import YoutubeTranscriptFetcher
from knowledge_pipeline.domain.models import CaptionSource


def _vtt(lang: str = "en") -> dict:
    return {lang: [{"ext": "srv3", "url": "u-srv3"}, {"ext": "vtt", "url": "u-vtt"}]}


def _non_vtt(lang: str = "en") -> dict:
    return {lang: [{"ext": "srv3", "url": "u-srv3"}, {"ext": "json3", "url": "u-json3"}]}


def test_has_usable_vtt_true_only_when_a_downloadable_vtt_exists():
    assert YoutubeTranscriptFetcher._has_usable_vtt(_vtt()) is True
    assert YoutubeTranscriptFetcher._has_usable_vtt(_non_vtt()) is False
    assert YoutubeTranscriptFetcher._has_usable_vtt({}) is False
    # listed but no url ⇒ not usable
    assert YoutubeTranscriptFetcher._has_usable_vtt({"en": [{"ext": "vtt"}]}) is False


def test_manual_listed_in_non_vtt_only_does_not_report_has_manual():
    # The exact WR-03 case: manual track exists but only as srv3; auto exists as vtt. Availability must
    # say has_manual=False so fallback_decision can prefer ASR over the noisy auto track.
    fetcher = YoutubeTranscriptFetcher()
    subs = _non_vtt()      # manual present but NOT vtt
    auto = _vtt()          # auto present AND vtt

    has_manual = fetcher._has_usable_vtt(subs)
    has_auto = fetcher._has_usable_vtt(auto)
    track, source = fetcher._pick_track(subs, auto)

    assert has_manual is False
    assert has_auto is True
    # the chosen track is the auto vtt, and reported availability agrees with the real picked source
    assert source is CaptionSource.AUTO
    assert track is not None and track["url"] == "u-vtt"


def test_usable_manual_vtt_is_reported_and_preferred():
    fetcher = YoutubeTranscriptFetcher()
    subs = _vtt()
    auto = _vtt()
    assert fetcher._has_usable_vtt(subs) is True
    track, source = fetcher._pick_track(subs, auto)
    assert source is CaptionSource.MANUAL  # manual preferred when it has a usable vtt
    assert track["url"] == "u-vtt"
