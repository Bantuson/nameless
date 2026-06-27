"""``parse_vtt`` — a pure WebVTT/SRT-ish timestamp parser for the yt-dlp subtitle fallback path.

The secondary fetch path (yt-dlp ``--write-subs``/``--write-auto-subs --sub-format vtt``) yields VTT
text, and YouTube auto-captions in particular are messy: rolling cues that repeat lines, inline
``<00:00:01.000>`` word timing tags, and ``align:``/``position:`` cue settings. Parsing them into clean
timestamped :class:`TranscriptSegment`s is fiddly but PURE — so it lives here, fully unit-testable,
instead of tangled inside the network adapter (STACK.md flags json3/ttml as buggy; VTT/SRT preferred).

We keep it deliberately small and robust: extract ``HH:MM:SS.mmm --> HH:MM:SS.mmm`` cue headers, strip
inline timing/markup tags from the cue body, collapse whitespace, and drop consecutive duplicate lines
(the auto-caption rolling-window artifact).
"""

from __future__ import annotations

import re

from ..domain.models import TranscriptSegment

# A cue header: 00:00:01.000 --> 00:00:04.000 [optional cue settings]
_CUE_TIME = re.compile(
    r"(?P<start>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(?P<end>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})"
)
# Inline markup: <c>, </c>, <00:00:01.000>, <v Author>, etc.
_INLINE_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _ts_to_seconds(ts: str) -> float:
    """Parse 'HH:MM:SS.mmm' / 'MM:SS.mmm' (',' or '.' for ms) into float seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    parts = [float(p) for p in parts]
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60.0 + p
    return round(seconds, 3)


def _clean_line(line: str) -> str:
    return _WS.sub(" ", _INLINE_TAG.sub("", line)).strip()


def parse_vtt(text: str) -> list[TranscriptSegment]:
    """Parse VTT/SRT subtitle text into de-duplicated, timestamped segments. Pure.

    Returns segments in time order. Consecutive cues whose cleaned text is identical to the previous kept
    line are dropped (the YouTube auto-caption rolling-window repeats every line ~twice).
    """
    if not text:
        return []

    lines = text.splitlines()
    segments: list[TranscriptSegment] = []
    i = 0
    n = len(lines)
    last_text = ""

    while i < n:
        line = lines[i].strip()
        m = _CUE_TIME.search(line)
        if not m:
            i += 1
            continue

        start_s = _ts_to_seconds(m.group("start"))
        end_s = _ts_to_seconds(m.group("end"))

        # Collect the cue body lines until a blank line or the next cue header.
        body_parts: list[str] = []
        i += 1
        while i < n and lines[i].strip() and not _CUE_TIME.search(lines[i]):
            cleaned = _clean_line(lines[i])
            if cleaned:
                body_parts.append(cleaned)
            i += 1

        body = _WS.sub(" ", " ".join(body_parts)).strip()
        if not body or body == last_text:
            continue
        last_text = body
        duration = max(0.0, round(end_s - start_s, 3))
        segments.append(
            TranscriptSegment(start_s=start_s, duration_s=duration, text=body)
        )

    return segments
