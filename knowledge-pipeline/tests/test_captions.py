"""parse_vtt tests — the pure VTT/SRT parser for the yt-dlp subtitle fallback path."""

from __future__ import annotations

from knowledge_pipeline.pure.captions import parse_vtt

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Let's high-pass the log drum.

00:00:04.500 --> 00:00:08.000
Sidechain the <00:00:05.000><c>bass</c> to the kick.
"""

# YouTube auto-caption style: rolling window repeats the previous line, inline timing tags.
AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.500 --> 00:00:02.000 align:start position:0%
roll off the

00:00:02.000 --> 00:00:03.500 align:start position:0%
roll off the<00:00:02.500><c> low</c><00:00:03.000><c> end</c>

00:00:03.500 --> 00:00:05.000 align:start position:0%
roll off the low end
"""


def test_parses_cue_times_and_text():
    segs = parse_vtt(VTT)
    assert len(segs) == 2
    assert segs[0].start_s == 1.0
    assert segs[0].text == "Let's high-pass the log drum."
    assert abs(segs[0].duration_s - 3.0) < 1e-6


def test_strips_inline_timing_and_markup_tags():
    segs = parse_vtt(VTT)
    assert segs[1].text == "Sidechain the bass to the kick."


def test_collapses_rolling_duplicate_lines():
    segs = parse_vtt(AUTO_VTT)
    texts = [s.text for s in segs]
    # the rolling window repeats; consecutive identical cleaned lines collapse to distinct content
    assert texts == ["roll off the", "roll off the low end"]


def test_empty_input_yields_no_segments():
    assert parse_vtt("") == []
    assert parse_vtt("WEBVTT\n\n") == []


def test_hms_and_ms_separators_parsed():
    vtt = "WEBVTT\n\n01:02:03.250 --> 01:02:05.750\nhello\n"
    segs = parse_vtt(vtt)
    assert segs[0].start_s == 3723.25  # 1h2m3.25s
    assert abs(segs[0].duration_s - 2.5) < 1e-6
