"""FixtureDiscoverySource — the fixture-backed :class:`~knowledge_pipeline.ports.DiscoverySource`.

Returns candidate :class:`VideoRef`s from an in-memory fixture set, matched to a query by genre/stage
(falling back to a title substring match), and stamps the query's discovery provenance onto each hit —
exactly as the real yt-dlp adapter must. This lets the discovery + dedup + grid-concentration logic be
tested with no network. It deliberately returns the SAME video for multiple overlapping queries so the
dedup path (KNOW-01) is exercised.
"""

from __future__ import annotations

from typing import Iterable

from ..domain.models import DiscoveryQuery, VideoRef


class FixtureDiscoverySource:
    """A deterministic discovery source over a fixed list of videos."""

    def __init__(self, videos: Iterable[VideoRef]) -> None:
        self._videos = list(videos)

    def search(self, query: DiscoveryQuery, limit: int) -> list[VideoRef]:
        matches: list[VideoRef] = []
        q_terms = set(query.text.lower().split())
        for v in self._videos:
            if self._matches(v, query, q_terms):
                # Stamp THIS query's provenance onto the hit (real adapter does the same).
                matches.append(
                    v.model_copy(
                        update={
                            "query_origin": query.text,
                            "genre": v.genre or query.genre,
                            "stage": v.stage or query.stage,
                            "artist_anchor": v.artist_anchor or query.artist_anchor,
                        }
                    )
                )
            if len(matches) >= limit:
                break
        return matches

    @staticmethod
    def _matches(v: VideoRef, query: DiscoveryQuery, q_terms: set[str]) -> bool:
        # Artist-anchored query: match the anchor name appearing in the title or the video's anchor field.
        if query.kind == "artist" and query.artist_anchor:
            anchor = query.artist_anchor.lower()
            if anchor in (v.title or "").lower() or (v.artist_anchor or "").lower() == anchor:
                return True
        # Grid query: match on genre (+ stage when both carry it), else a loose title-term overlap.
        if query.genre and v.genre and query.genre == v.genre:
            if not query.stage or not v.stage or query.stage == v.stage:
                return True
        title_terms = set((v.title or "").lower().split())
        return len(q_terms & title_terms) >= 2
