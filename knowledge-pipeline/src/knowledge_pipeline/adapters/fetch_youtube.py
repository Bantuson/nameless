"""YoutubeTranscriptFetcher — the REAL :class:`~knowledge_pipeline.ports.TranscriptFetcher`.

Two paths, primary then secondary (STACK.md / research ingestion flow):
  1. **youtube-transcript-api (1.x)** — the clean captions fast path. List the video's transcripts,
     PREFER a manually-created one, else a generated (auto) one; fetch it into timestamped segments.
  2. **yt-dlp subtitles** — the robust fallback when (1) 403s / is blocked / finds nothing. Ask yt-dlp
     for the subtitle/auto-caption track URLs (``--write-subs --write-auto-subs --sub-format vtt``),
     download the VTT, and parse it with the pure :func:`parse_vtt`.

Either way the result is a :class:`CaptionFetch`: the availability (manual? auto? a cheap auto-quality
proxy) that :func:`fallback_decision` reasons over, plus the best transcript actually pulled (or ``None``
if only ASR can recover anything).

WHY THE IMPORTS ARE LAZY (inside methods): the 4GB box installs neither library and the suite runs on
:class:`FixtureTranscriptFetcher`; importing this module must stay free. ToS / local-first: run from a
HOME IP, throttled by the pipeline's RateLimiter (PITFALLS #2 — datacenter IPs are blocked).
"""

from __future__ import annotations

import logging
import urllib.request
from typing import Optional

from ..domain.models import (
    CaptionAvailability,
    CaptionFetch,
    CaptionSource,
    RawTranscript,
    TranscriptSegment,
    VideoRef,
)
from ..pure.captions import parse_vtt

logger = logging.getLogger("knowledge_pipeline.fetch_youtube")

# Preferred caption languages, in order (English-first; the north-star R&B/house material is English,
# amapiano/SA content is code-switched English+isiZulu/Sesotho — 'en' auto-captions still help).
DEFAULT_LANGUAGES = ("en", "en-US", "en-GB")


class YoutubeTranscriptFetcher:
    """Real captions fetch: youtube-transcript-api primary, yt-dlp subtitles secondary."""

    def __init__(
        self,
        *,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        use_ytdlp_fallback: bool = True,
    ) -> None:
        self._languages = languages
        self._use_ytdlp_fallback = use_ytdlp_fallback

    # ---- port ----
    def fetch(self, video: VideoRef) -> CaptionFetch:
        vid = video.video_id
        # 1) primary: youtube-transcript-api
        try:
            result = self._fetch_via_transcript_api(vid)
            if result is not None:
                return result
        except Exception as exc:  # noqa: BLE001 - any failure (incl. IP block) falls through to yt-dlp
            logger.warning("youtube-transcript-api failed for %s: %s", vid, exc)

        # 2) secondary: yt-dlp subtitles
        if self._use_ytdlp_fallback:
            try:
                result = self._fetch_via_ytdlp(vid)
                if result is not None:
                    return result
            except Exception as exc:  # noqa: BLE001
                logger.warning("yt-dlp subtitle fallback failed for %s: %s", vid, exc)

        # nothing recoverable from captions — report no availability so the pipeline tries ASR
        return CaptionFetch(
            video_id=vid,
            availability=CaptionAvailability(has_manual=False, has_auto=False),
            transcript=None,
        )

    # ---- primary path -----------------------------------------------------------------------
    def _fetch_via_transcript_api(self, video_id: str) -> Optional[CaptionFetch]:
        from youtube_transcript_api import YouTubeTranscriptApi  # lazy

        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)  # 1.x instance API -> TranscriptList

        has_manual = False
        has_auto = False
        manual_t = None
        auto_t = None
        for t in transcript_list:
            if getattr(t, "is_generated", False):
                has_auto = True
                if auto_t is None:
                    auto_t = t
            else:
                has_manual = True
                if manual_t is None:
                    manual_t = t

        # Prefer a manual transcript in a preferred language if available.
        chosen = None
        source = CaptionSource.NONE
        try:
            chosen = transcript_list.find_manually_created_transcript(list(self._languages))
            source = CaptionSource.MANUAL
        except Exception:  # noqa: BLE001 - no manual in preferred langs; try generated
            try:
                chosen = transcript_list.find_generated_transcript(list(self._languages))
                source = CaptionSource.AUTO
            except Exception:  # noqa: BLE001 - fall back to whatever we enumerated
                chosen = manual_t or auto_t
                source = CaptionSource.MANUAL if chosen is manual_t and manual_t else CaptionSource.AUTO

        if chosen is None:
            return None

        segments = self._segments_from_fetched(chosen.fetch())
        language = getattr(chosen, "language_code", "en")
        transcript = RawTranscript(
            video_id=video_id,
            caption_source=source,
            language=language,
            fetched_via="youtube-transcript-api",
            segments=segments,
        )
        auto_quality = _cheap_auto_quality(transcript) if source is CaptionSource.AUTO else None
        return CaptionFetch(
            video_id=video_id,
            availability=CaptionAvailability(
                has_manual=has_manual, has_auto=has_auto, auto_quality=auto_quality
            ),
            transcript=transcript,
        )

    @staticmethod
    def _segments_from_fetched(fetched) -> list[TranscriptSegment]:
        """Normalize a youtube-transcript-api FetchedTranscript (1.x objects OR legacy dicts)."""
        # 1.x FetchedTranscript supports .to_raw_data(); older returns a list[dict] directly.
        raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
        segments: list[TranscriptSegment] = []
        for item in raw:
            if isinstance(item, dict):
                start = item.get("start", 0.0)
                dur = item.get("duration")
                text = item.get("text", "")
            else:  # snippet object
                start = getattr(item, "start", 0.0)
                dur = getattr(item, "duration", None)
                text = getattr(item, "text", "")
            text = (text or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    start_s=float(start),
                    duration_s=(float(dur) if dur is not None else None),
                    text=text,
                )
            )
        return segments

    # ---- secondary path ---------------------------------------------------------------------
    def _fetch_via_ytdlp(self, video_id: str) -> Optional[CaptionFetch]:
        from yt_dlp import YoutubeDL  # lazy

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
            "subtitleslangs": list(self._languages),
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        subs = (info or {}).get("subtitles") or {}
        auto = (info or {}).get("automatic_captions") or {}
        # WR-03: availability must reflect what _pick_track can ACTUALLY obtain — a downloadable ``vtt``
        # track — not merely that a track is *listed*. A video may list a manual track in a non-vtt format
        # (e.g. srv3) while only its auto track is vtt; `bool(subs)` would report has_manual=True, the
        # picked transcript would be AUTO, and `fallback_decision` would wrongly skip ASR for a noisy auto
        # track. Deriving from usable vtt presence keeps the decision (and the reported source) honest.
        has_manual = self._has_usable_vtt(subs)
        has_auto = self._has_usable_vtt(auto)

        track, source = self._pick_track(subs, auto)
        if track is None:
            return None

        vtt_text = self._download_text(track["url"])
        segments = parse_vtt(vtt_text)
        if not segments:
            return None

        transcript = RawTranscript(
            video_id=video_id,
            caption_source=source,
            language=track.get("lang", "en"),
            fetched_via="yt-dlp-subs",
            segments=segments,
        )
        auto_quality = _cheap_auto_quality(transcript) if source is CaptionSource.AUTO else None
        return CaptionFetch(
            video_id=video_id,
            availability=CaptionAvailability(
                has_manual=has_manual, has_auto=has_auto, auto_quality=auto_quality
            ),
            transcript=transcript,
        )

    @staticmethod
    def _has_usable_vtt(langs: dict) -> bool:
        """True iff some language offers a downloadable ``vtt`` track — what _pick_track can use (WR-03).

        Consistent with _pick_track's own filter (``ext == "vtt"`` and a non-empty ``url``), so
        ``has_manual`` is True exactly when _pick_track would return a MANUAL source from ``subs``.
        """
        for fmts in (langs or {}).values():
            for fmt in (fmts or []):
                if fmt.get("ext") == "vtt" and fmt.get("url"):
                    return True
        return False

    def _pick_track(self, subs: dict, auto: dict):
        """Choose a VTT track URL, preferring manual subs over automatic captions, in language order."""
        for langs, source in ((subs, CaptionSource.MANUAL), (auto, CaptionSource.AUTO)):
            for lang in (*self._languages, *langs.keys()):
                fmts = langs.get(lang)
                if not fmts:
                    continue
                for fmt in fmts:
                    if fmt.get("ext") == "vtt" and fmt.get("url"):
                        return {"url": fmt["url"], "lang": lang}, source
        return None, CaptionSource.NONE

    @staticmethod
    def _download_text(url: str) -> str:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - YouTube CDN URL from yt-dlp
            return resp.read().decode("utf-8", errors="replace")


def _cheap_auto_quality(transcript: RawTranscript) -> float:
    """A lightweight 0..1 proxy of auto-caption quality (NOT the full extractability score).

    Two cheap signals that distinguish usable auto-captions from garbage, without importing the scorer:
      * punctuation presence — auto-captions with sentence punctuation tend to be the better-segmented
        ones; pure stream-of-words auto-captions are worse.
      * word density — a track with almost no words over a long video is the visual-only tell.
    Kept deliberately crude: it only gates the "is it worth re-ASR-ing this auto track?" decision.
    """
    text = transcript.full_text()
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    punct = sum(text.count(p) for p in ".?!,")
    punct_ratio = min(1.0, punct / max(1, len(words) / 12.0))  # ~1 mark per 12 words ⇒ saturates
    dur_min = max(transcript.duration_s() / 60.0, 1e-6)
    wpm = len(words) / dur_min
    density = min(1.0, wpm / 120.0)
    return round(0.5 * punct_ratio + 0.5 * density, 4)
