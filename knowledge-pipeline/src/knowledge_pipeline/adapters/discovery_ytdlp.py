"""YtDlpDiscoverySource — the REAL :class:`~knowledge_pipeline.ports.DiscoverySource` (yt-dlp ytsearch).

Resolves a discovery query to candidate videos via ``yt-dlp``'s ``ytsearch{N}:{query}`` with FLAT
extraction — metadata only (id, title, channel, duration), NO media download. This is the cheapest,
most robust discovery path (STACK.md: yt-dlp is the most robust, actively-maintained tool; pin it).

WHY THE IMPORT IS LAZY (inside :meth:`search`): the 4GB build box does not install yt-dlp, and the whole
test suite runs against :class:`FixtureDiscoverySource`. Importing this module must stay free, so
``yt_dlp`` is imported only when :meth:`search` actually runs (the env-gated, home-IP path).

ToS / local-first (README): yt-dlp is unofficial and against YouTube ToS at scale; run from a HOME/
residential IP (datacenter IPs get ``RequestBlocked`` instantly — PITFALLS #2). This adapter does the
network; the pipeline throttles it via the injected RateLimiter.
"""

from __future__ import annotations

import logging

from ..domain.models import DiscoveryQuery, VideoRef

logger = logging.getLogger("knowledge_pipeline.discovery_ytdlp")


class YtDlpDiscoverySource:
    """Real discovery via yt-dlp flat search. Stateless; one instance can run many queries."""

    def __init__(self, *, quiet: bool = True) -> None:
        self._quiet = quiet

    def search(self, query: DiscoveryQuery, limit: int) -> list[VideoRef]:
        from yt_dlp import YoutubeDL  # lazy (env-gated)

        opts = {
            "quiet": self._quiet,
            "no_warnings": self._quiet,
            "skip_download": True,
            "extract_flat": True,   # metadata only — do NOT resolve each entry's full page
            "default_search": "ytsearch",
        }
        search_term = f"ytsearch{int(limit)}:{query.text}"

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_term, download=False)

        entries = (info or {}).get("entries", []) or []
        refs: list[VideoRef] = []
        for entry in entries:
            if not entry:
                continue
            video_id = entry.get("id")
            if not video_id:
                continue
            duration = entry.get("duration")
            refs.append(
                VideoRef(
                    video_id=str(video_id),
                    title=entry.get("title") or "",
                    channel=entry.get("channel") or entry.get("uploader"),
                    duration_s=int(duration) if isinstance(duration, (int, float)) else None,
                    query_origin=query.text,
                    genre=query.genre,
                    stage=query.stage,
                    artist_anchor=query.artist_anchor,
                )
            )
        logger.info("ytsearch %r -> %d candidates", query.text, len(refs))
        return refs
