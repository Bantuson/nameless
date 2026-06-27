"""MiningPipeline — the Phase-4 orchestration, pure over injected ports (KNOW-05/06).

Like the Phase-3 ``IngestPipeline``, this contains NO ``anthropic``, NO sqlite, NO embeddings, NO clock.
It wires the ports in the one correct order and turns the Phase-3 snapshot corpus into a cited,
cross-referenced claim layer:

    for each target video:
        load snapshot (CorpusStore.load_snapshot)            [the immutable Phase-3 evidence]
        extract  -> list[Claim]    (ClaimExtractor)          [KNOW-05: atomic, cited, no synthesis]
        bind citation: verify_citation(claim, snapshot)      [KNOW-05 #2: precursor to Phase-5 gate]
    dedup_claims(all)              (optional SimilarityIndex) [KNOW-06: distinct sources, not repeats]
    upsert_claims                  (ClaimStore, idempotent)
    cross_reference(ALL claims)    -> clusters               [KNOW-06: consensus XOR preserved conflict]
    replace_clusters               (ClaimStore)              [clusters are global; recomputed each run]

Two deliberate design points:
  * **No synthesis.** The pipeline only extracts, verifies, dedups, groups, persists. It never decides a
    "best way" or collapses a conflict — that boundary is the phase, and it is a tested invariant.
  * **Clusters are recomputed globally** over the full stored claim set after every mine (then replaced),
    so consensus/conflict stay correct even when mining runs incrementally over a subset of videos.

Every dependency is a port, so the whole flow runs in tests with a FakeClaimExtractor + InMemoryClaimStore
+ an in-memory corpus — no API, no tokens, no DB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

from pydantic import BaseModel, Field

from .domain.claims import Claim
from .ports import ClaimExtractor, ClaimStore, CorpusStore, SimilarityIndex
from .pure.citation import verify_citation
from .pure.claim_dedup import dedup_claims
from .pure.cross_reference import cross_reference

logger = logging.getLogger("knowledge_pipeline.mining")


@dataclass(frozen=True)
class MineTarget:
    """One video to mine + its discovery-provenance genres (context for the extractor)."""

    video_id: str
    genres: list[str] = field(default_factory=list)


@dataclass
class MiningConfig:
    """Knobs for one mining run."""

    citation_tolerance_ms: int = 2000      # how far a quote may sit from its cited ts before it's drift
    citation_min_coverage: float = 0.8     # min token coverage to accept a non-substring quote match
    require_citation: bool = False         # if True, DROP claims whose citation fails (else keep + flag)
    semantic_dedup: bool = False           # if True, use the injected SimilarityIndex for same-source dedup
    semantic_threshold: float = 0.9


class MineOutcome(BaseModel):
    """Compact per-video result — safe to log/print (no transcript dump)."""

    video_id: str
    extracted: int = 0
    citations_ok: int = 0
    citations_failed: int = 0
    kept: int = 0
    detail: str = ""


class MiningReport(BaseModel):
    """The roll-up of a mining run."""

    outcomes: list[MineOutcome] = Field(default_factory=list)
    total_claims: int = 0
    total_clusters: int = 0
    contested_clusters: int = 0
    duplicates_dropped: int = 0


class MiningPipeline:
    """Orchestrates snapshot corpus -> cited, cross-referenced claim layer. Stateless; reusable."""

    def __init__(
        self,
        extractor: ClaimExtractor,
        store: ClaimStore,
        corpus: CorpusStore,
        *,
        similarity: Optional[SimilarityIndex] = None,
        config: Optional[MiningConfig] = None,
    ) -> None:
        self._extractor = extractor
        self._store = store
        self._corpus = corpus
        self._similarity = similarity
        self._config = config or MiningConfig()

    def mine(self, targets: Sequence[MineTarget]) -> MiningReport:
        """Extract -> verify -> dedup -> persist -> (globally) cross-reference. Idempotent re-runs."""
        self._store.init_schema()
        cfg = self._config

        new_claims: list[Claim] = []
        verified: dict[str, bool] = {}
        outcomes: list[MineOutcome] = []

        for target in targets:
            snapshot = self._corpus.load_snapshot(target.video_id)
            if snapshot is None:
                outcomes.append(MineOutcome(video_id=target.video_id, detail="no snapshot in corpus"))
                continue
            try:
                claims = self._extractor.extract(snapshot, genres=target.genres)
            except Exception as exc:  # noqa: BLE001 - one bad video must not sink the whole run
                logger.warning("extraction failed for %s: %s", target.video_id, exc)
                outcomes.append(MineOutcome(video_id=target.video_id, detail=f"extract error: {exc}"))
                continue

            ok = failed = 0
            kept_for_video: list[Claim] = []
            for c in claims:
                chk = verify_citation(
                    c, snapshot,
                    tolerance_ms=cfg.citation_tolerance_ms,
                    min_coverage=cfg.citation_min_coverage,
                )
                verified[c.id] = chk.ok
                if chk.ok:
                    ok += 1
                else:
                    failed += 1
                if cfg.require_citation and not chk.ok:
                    continue  # honest drop; Phase 5's gate is where this becomes a hard reject
                kept_for_video.append(c)

            new_claims.extend(kept_for_video)
            outcomes.append(
                MineOutcome(
                    video_id=target.video_id,
                    extracted=len(claims),
                    citations_ok=ok,
                    citations_failed=failed,
                    kept=len(kept_for_video),
                )
            )

        # ---- dedup (distinct sources, not repeats) ----
        sim_fn = self._similarity.similarity if (self._similarity and cfg.semantic_dedup) else None
        deduped, dropped = dedup_claims(new_claims, similarity=sim_fn, threshold=cfg.semantic_threshold)
        self._store.upsert_claims(deduped, verified=verified)

        # ---- cross-reference GLOBALLY over all stored claims, then replace ----
        all_claims = self._store.list_claims()
        clusters = cross_reference(all_claims)
        self._store.replace_clusters(clusters)

        contested = sum(1 for cl in clusters if cl.is_contested)
        report = MiningReport(
            outcomes=outcomes,
            total_claims=len(all_claims),
            total_clusters=len(clusters),
            contested_clusters=contested,
            duplicates_dropped=dropped,
        )
        logger.info(
            "mine: %d claims, %d clusters (%d contested), %d duplicates dropped",
            report.total_claims, report.total_clusters, report.contested_clusters, report.duplicates_dropped,
        )
        return report
