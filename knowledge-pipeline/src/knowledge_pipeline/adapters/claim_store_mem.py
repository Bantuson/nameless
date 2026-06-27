"""InMemoryClaimStore — the RAM-safe fake for :class:`~knowledge_pipeline.ports.ClaimStore`.

Plain dicts; no sqlite, no filesystem. A FAITHFUL double for the sqlite store: same idempotent upsert by
claim id, same global ``replace_clusters`` semantics, same filter/sort on ``list_claims`` /
``list_clusters``, and the same ``stats`` roll-up — so a pipeline/store test written against this fake
proves the behavior the real store reproduces, with zero I/O.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..domain.claims import Claim, ClaimCluster, ClaimStats


class InMemoryClaimStore:
    """An in-memory claim + cluster store."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._verified: dict[str, bool] = {}
        self._clusters: dict[str, ClaimCluster] = {}

    def init_schema(self) -> None:
        return None

    # ---- claims ----
    def upsert_claims(self, claims: Iterable[Claim], *, verified: Optional[dict[str, bool]] = None) -> int:
        verified = verified or {}
        n = 0
        for c in claims:
            self._claims[c.id] = c
            self._verified[c.id] = bool(verified.get(c.id, self._verified.get(c.id, False)))
            n += 1
        return n

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        return self._claims.get(claim_id)

    def list_claims(
        self,
        *,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
        technique: Optional[str] = None,
        source_video_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> list[Claim]:
        rows = list(self._claims.values())
        if stage is not None:
            rows = [c for c in rows if c.stage == stage]
        if technique is not None:
            rows = [c for c in rows if c.technique == technique]
        if source_video_id is not None:
            rows = [c for c in rows if c.source_video_id == source_video_id]
        if genre is not None:
            rows = [c for c in rows if genre in c.genre]
        if min_confidence is not None:
            rows = [c for c in rows if c.confidence >= min_confidence]
        # stable, deterministic order for inspection
        rows.sort(key=lambda c: (c.topic, c.source_video_id, c.timestamp_ms))
        return rows

    def is_verified(self, claim_id: str) -> bool:
        return self._verified.get(claim_id, False)

    # ---- clusters (global; replaced wholesale) ----
    def replace_clusters(self, clusters: Iterable[ClaimCluster]) -> int:
        self._clusters = {cl.topic: cl for cl in clusters}
        return len(self._clusters)

    def get_cluster(self, topic: str) -> Optional[ClaimCluster]:
        return self._clusters.get(topic)

    def list_clusters(
        self,
        *,
        contested_only: bool = False,
        stage: Optional[str] = None,
        genre: Optional[str] = None,
    ) -> list[ClaimCluster]:
        rows = list(self._clusters.values())
        if contested_only:
            rows = [cl for cl in rows if cl.is_contested]
        if stage is not None:
            rows = [cl for cl in rows if cl.stage == stage]
        if genre is not None:
            rows = [cl for cl in rows if genre in cl.genre]
        rows.sort(key=lambda cl: cl.topic)
        return rows

    # ---- stats ----
    def stats(self) -> ClaimStats:
        by_stage: dict[str, int] = {}
        by_genre: dict[str, int] = {}
        by_caption: dict[str, int] = {}
        verified = 0
        for c in self._claims.values():
            by_stage[c.stage] = by_stage.get(c.stage, 0) + 1
            for g in (c.genre or ["unknown"]):
                by_genre[g] = by_genre.get(g, 0) + 1
            cs = c.caption_source.value
            by_caption[cs] = by_caption.get(cs, 0) + 1
            if self._verified.get(c.id):
                verified += 1
        contested = sum(1 for cl in self._clusters.values() if cl.is_contested)
        return ClaimStats(
            total_claims=len(self._claims),
            total_clusters=len(self._clusters),
            contested_clusters=contested,
            citation_verified=verified,
            by_stage=by_stage,
            by_genre=by_genre,
            by_caption_source=by_caption,
        )
