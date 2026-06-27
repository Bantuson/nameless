"""IngestPipeline — the Phase-3 orchestration, pure over injected ports.

This is the heart of the ingestion stage, and like the Phase-2 ``AnalyzeJobConsumer`` it contains NO
yt-dlp, NO youtube-transcript-api, NO faster-whisper, NO sqlite. It wires the ports in the one correct
order and drives the corpus build:

    discover  → for each query: throttle, search; then DEDUP by video_id (merge provenance)   [KNOW-01]
    ingest    → drop already-ingested (idempotent); for each fresh video:
                  throttle → fetch captions → fallback_decision                                [KNOW-03]
                    ├─ USE_CAPTIONS   → use the fetched transcript
                    ├─ FETCH_AND_ASR  → throttle → transcribe (faster-whisper)                  [KNOW-03]
                    └─ REJECT         → an empty (caption_source=none) transcript
                  snapshot_record(transcript, clock.now())   (sha256 + retrieval date)          [KNOW-02]
                  extractability_score(transcript)            (0..1 + flags + verdict)           [KNOW-03]
                  store.write_snapshot + store.register       (immutable file + registry row)    [KNOW-02/04]

Because every dependency is a port, the entire flow — discovery, dedup, the fallback ladder, ASR
invocation, snapshotting, scoring, and registry persistence — is exercised in tests with deterministic
fakes + a virtual clock. The real adapters swap in unchanged (ports-and-adapters law).

Every video that is looked at produces a registry row (even a hard reject), so the corpus is the FULL,
honest record — "we looked, here is what was teachable and what was not" — which is exactly the
visual-only-flagging discipline KNOW-03 demands (don't fake low-signal sources into the corpus silently).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .domain.models import (
    CaptionSource,
    CorpusEntry,
    DiscoveryQuery,
    FallbackAction,
    IngestOutcome,
    IngestReport,
    IngestStatus,
    RawTranscript,
    Verdict,
    VideoRef,
)
from .ports import Clock, CorpusStore, DiscoverySource, RateLimiter, TranscriptFetcher, Transcriber
from .pure.dedup import dedup_already_ingested, dedup_video_refs
from .pure.extractability import DEFAULT_CONFIG, ScoringConfig, extractability_score
from .pure.fallback import fallback_decision
from .pure.snapshot import snapshot_record

logger = logging.getLogger("knowledge_pipeline.pipeline")


@dataclass
class PipelineConfig:
    """Knobs for one ingest run (sane defaults; overridable by the CLI / a calibration pass)."""

    results_per_query: int = 5          # yt-dlp ytsearch fan-out per query (grid x this ⇒ candidate pool)
    asr_enabled: bool = True            # whether the ASR fallback is available this run ([asr] installed)
    auto_quality_floor: float = 0.5     # min auto-caption proxy quality to use auto as-is (else ASR)
    scoring: ScoringConfig = field(default_factory=lambda: DEFAULT_CONFIG)
    register_rejected: bool = True      # record hard-rejects too (honest corpus + idempotent skip)


class IngestPipeline:
    """Orchestrates discovery → snapshotted, scored corpus. Stateless; safe to reuse across runs."""

    def __init__(
        self,
        discovery: DiscoverySource,
        fetcher: TranscriptFetcher,
        transcriber: Transcriber,
        store: CorpusStore,
        rate_limiter: RateLimiter,
        clock: Clock,
        *,
        config: PipelineConfig | None = None,
    ) -> None:
        self._discovery = discovery
        self._fetcher = fetcher
        self._transcriber = transcriber
        self._store = store
        self._throttle = rate_limiter
        self._clock = clock
        self._config = config or PipelineConfig()

    # ---- discovery + dedup (KNOW-01) ----------------------------------------------------------
    def discover(self, queries: Sequence[DiscoveryQuery]) -> list[VideoRef]:
        """Run every query (throttled) and return the de-duplicated candidate set (provenance merged)."""
        raw: list[VideoRef] = []
        for query in queries:
            self._throttle.acquire()
            try:
                hits = self._discovery.search(query, self._config.results_per_query)
            except Exception as exc:  # noqa: BLE001 - one bad query must not sink the whole discovery run
                logger.warning("discovery failed for %r: %s", query.text, exc)
                continue
            raw.extend(hits)
        unique, dupes = dedup_video_refs(raw)
        logger.info("discovery: %d raw hits -> %d unique (%d duplicates merged)", len(raw), len(unique), dupes)
        return unique

    # ---- ingest (KNOW-02/03/04) ---------------------------------------------------------------
    def ingest(self, videos: Sequence[VideoRef]) -> IngestReport:
        """Fetch+fallback+snapshot+score+register each video; idempotently skip already-ingested ones."""
        self._store.init_schema()
        fresh, _already = dedup_already_ingested(videos, self._store.known_ids())
        fresh_ids = {f.video_id for f in fresh}

        # Already-in-corpus videos are reported as idempotent skips (no re-fetch).
        outcomes: list[IngestOutcome] = [
            IngestOutcome(
                video_id=v.video_id,
                status=IngestStatus.SKIPPED_DUPLICATE,
                detail="already in corpus",
            )
            for v in videos
            if v.video_id not in fresh_ids
        ]

        # Fresh videos go through fetch+fallback+snapshot+score+register.
        for video in fresh:
            outcomes.append(self._ingest_one(video))

        report = IngestReport(outcomes=outcomes)
        logger.info(
            "ingest: %d ingested, %d rejected, %d skipped, %d errored (of %d)",
            report.ingested, report.rejected, report.skipped, report.errored, len(videos),
        )
        return report

    def run(self, queries: Sequence[DiscoveryQuery]) -> IngestReport:
        """Convenience: discover then ingest in one call."""
        return self.ingest(self.discover(queries))

    # ---- one video ----------------------------------------------------------------------------
    def _ingest_one(self, video: VideoRef) -> IngestOutcome:
        try:
            self._throttle.acquire()
            fetch = self._fetcher.fetch(video)
            decision = fallback_decision(
                fetch.availability,
                asr_enabled=self._config.asr_enabled,
                auto_quality_floor=self._config.auto_quality_floor,
            )

            transcript = self._resolve_transcript(video, fetch, decision.action)

            now = self._clock.now()
            record = snapshot_record(transcript, now)
            extr = extractability_score(transcript, self._config.scoring)

            is_reject = extr.verdict is Verdict.REJECT
            if is_reject and not self._config.register_rejected:
                return IngestOutcome(
                    video_id=video.video_id,
                    status=IngestStatus.REJECTED,
                    verdict=extr.verdict,
                    score=extr.score,
                    caption_source=transcript.caption_source,
                    detail=f"rejected (not registered): {', '.join(extr.flags) or decision.reason}",
                )

            self._store.write_snapshot(transcript, record)
            entry = CorpusEntry(
                video=video,
                snapshot=record,
                extractability=extr,
                ingested_at=now,
            )
            self._store.register(entry)

            status = IngestStatus.REJECTED if is_reject else IngestStatus.INGESTED
            return IngestOutcome(
                video_id=video.video_id,
                status=status,
                verdict=extr.verdict,
                score=extr.score,
                caption_source=transcript.caption_source,
                detail=", ".join(extr.flags) if extr.flags else decision.reason,
            )
        except Exception as exc:  # noqa: BLE001 - normalize any adapter failure into a retryable ERROR
            logger.warning("ingest failed for %s: %s", video.video_id, exc)
            return IngestOutcome(
                video_id=video.video_id,
                status=IngestStatus.ERROR,
                detail=str(exc),
            )

    def _resolve_transcript(
        self,
        video: VideoRef,
        fetch,  # CaptionFetch
        action: FallbackAction,
    ) -> RawTranscript:
        """Turn the fallback action into the actual transcript to snapshot+score."""
        if action is FallbackAction.USE_CAPTIONS and fetch.transcript is not None:
            return fetch.transcript
        if action is FallbackAction.FETCH_AND_ASR:
            self._throttle.acquire()  # ASR pulls audio — a second network op, throttled too
            return self._transcriber.transcribe(video)
        # REJECT (or an inconsistent USE_CAPTIONS with no transcript): an empty, honestly-NONE transcript.
        return RawTranscript(
            video_id=video.video_id,
            caption_source=CaptionSource.NONE,
            language="en",
            fetched_via="none",
            segments=[],
        )
