"""``corpus`` CLI — discover, ingest, and inspect the tutorial corpus. Compact output by construction.

Subcommands:
  * ``corpus discover``  — build the (genre x stage) grid + anchors and resolve candidate videos
                           (the discovery PLAN + queue), without ingesting. [KNOW-01]
  * ``corpus ingest``    — run the full pipeline: discover -> fetch+fallback+ASR -> snapshot -> score
                           -> register, throttled + idempotent. [KNOW-02/03/04]
  * ``corpus list``      — inspect the registry: ``--by-genre`` / ``--by-extractability`` + filters.
  * ``corpus show``      — one entry + (optionally) the first N timestamped snapshot segments (the
                           Phase-4 ``video_id @ ts`` citation substrate). [KNOW-02]
  * ``corpus stats``     — compact corpus roll-up (total / by verdict / by genre) — answers KNOW-04.

Two run modes:
  * ``--fixtures [DIR]`` (default DIR = bundled fixtures) — OFFLINE: fake discovery/fetch/ASR over the
    fixture corpus + a no-op throttle. Runs anywhere with the light base install; great for a demo/CI.
  * live (no ``--fixtures``) — the REAL yt-dlp / youtube-transcript-api / faster-whisper adapters,
    throttled. ENV-GATED: needs ``uv sync --extra ingest --extra asr`` and a HOME IP (see README).

Output stays compact (token strategy): one terse line per video, never a transcript/segment dump unless
``corpus show --segments N`` is explicitly asked for.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
from typing import Optional

from .domain.genres import GENRES, STAGES
from .domain.models import CorpusEntry, IngestReport, Verdict, VideoRef
from .pipeline import IngestPipeline, PipelineConfig
from .pure.query_grid import query_grid

DEFAULT_CORPUS_ROOT = os.path.join(".nameless-knowledge", "corpus")


# ---------------------------------------------------------------------------------------------
# Plane construction
# ---------------------------------------------------------------------------------------------
def _build_store(root: str):
    from .adapters.corpus_fs import FilesystemCorpusStore

    return FilesystemCorpusStore(root)


def _build_queries(args: argparse.Namespace):
    genres = args.genres or list(GENRES)
    stages = args.stages or list(STAGES)
    return query_grid(stages=stages, genres=genres, expand_synonyms=args.expand_synonyms)


def _build_pipeline(args: argparse.Namespace) -> IngestPipeline:
    """Build the pipeline for either fixtures (offline) or the live env-gated adapters."""
    store = _build_store(args.corpus_root)
    config = PipelineConfig(
        results_per_query=args.limit,
        asr_enabled=not args.no_asr,
    )

    if args.fixtures is not None:
        from .adapters import (
            FixedTextTranscriber,
            FixtureDiscoverySource,
            FixtureTranscriptFetcher,
            NoOpRateLimiter,
            SystemClock,
        )
        from .fixtures import DEFAULT_FIXTURE_DIR, load_fixture_corpus

        fixture_dir = args.fixtures or str(DEFAULT_FIXTURE_DIR)
        corpus = load_fixture_corpus(fixture_dir)
        return IngestPipeline(
            discovery=FixtureDiscoverySource(corpus.videos),
            fetcher=FixtureTranscriptFetcher(corpus.fetches),
            transcriber=FixedTextTranscriber(corpus.asr),
            store=store,
            rate_limiter=NoOpRateLimiter(),
            clock=SystemClock(),
            config=config,
        )

    # ---- live (env-gated) ----
    _require_module("yt_dlp", "ingest")
    _require_module("youtube_transcript_api", "ingest")
    if not args.no_asr:
        _require_module("faster_whisper", "asr")

    from .adapters import IntervalRateLimiter, SystemClock
    from .adapters.discovery_ytdlp import YtDlpDiscoverySource
    from .adapters.fetch_youtube import YoutubeTranscriptFetcher
    from .adapters.transcribe_whisper import FasterWhisperTranscriber

    clock = SystemClock()
    return IngestPipeline(
        discovery=YtDlpDiscoverySource(),
        fetcher=YoutubeTranscriptFetcher(),
        transcriber=FasterWhisperTranscriber(),
        store=store,
        rate_limiter=IntervalRateLimiter(clock, min_interval_s=args.min_interval, jitter_s=args.jitter),
        clock=clock,
        config=config,
    )


def _require_module(module: str, extra: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise SystemExit(
            f"'{module}' is not installed. Live ingest is env-gated:\n"
            f"  uv sync --extra ingest --extra asr\n"
            f"(or run offline against fixtures with --fixtures). See README 'Verification'."
        )


# ---------------------------------------------------------------------------------------------
# Compact output
# ---------------------------------------------------------------------------------------------
def _fmt_video_line(v: VideoRef) -> str:
    cell = "/".join(p for p in (v.genre, v.stage) if p) or "-"
    return f"{v.video_id:<26}  {cell:<22}  {v.title[:46]}"


def _fmt_entry_line(e: CorpusEntry) -> str:
    x = e.extractability
    cell = "/".join(p for p in (e.video.genre, e.video.stage) if p) or "-"
    flags = ",".join(x.flags) if x.flags else "-"
    return (
        f"{e.video.video_id:<26}  {cell:<20}  {x.verdict.value:<10}  "
        f"{x.score:.2f}  {e.snapshot.caption_source.value:<6}  {flags}"
    )


def _print_report(report: IngestReport, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json(indent=2))
        return
    print(
        f"ingested={report.ingested}  rejected={report.rejected}  "
        f"skipped={report.skipped}  errored={report.errored}  total={len(report.outcomes)}"
    )
    for o in report.outcomes:
        score = f"{o.score:.2f}" if o.score is not None else "-"
        verdict = o.verdict.value if o.verdict else "-"
        print(f"  {o.video_id:<26}  {o.status.value:<18}  {verdict:<10}  {score}  {o.detail[:42]}")


# ---------------------------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------------------------
def _handle_discover(args: argparse.Namespace) -> int:
    queries = _build_queries(args)
    pipeline = _build_pipeline(args)
    videos = pipeline.discover(queries)
    if args.json:
        print(json.dumps([v.model_dump(mode="json") for v in videos], indent=2))
    else:
        print(f"# {len(queries)} queries -> {len(videos)} unique candidate videos")
        for v in videos:
            print(_fmt_video_line(v))
    return 0


def _handle_ingest(args: argparse.Namespace) -> int:
    queries = _build_queries(args)
    pipeline = _build_pipeline(args)
    report = pipeline.run(queries)
    _print_report(report, args.json)
    return 0


def _handle_list(args: argparse.Namespace) -> int:
    store = _build_store(args.corpus_root)
    store.init_schema()
    verdict = Verdict(args.verdict) if args.verdict else None
    entries = store.list_entries(
        genre=args.genre,
        verdict=verdict,
        min_score=args.min_score,
        order_by_score=args.by_extractability,
    )

    if args.json:
        print(json.dumps([e.model_dump(mode="json") for e in entries], indent=2))
        return 0

    if args.by_genre:
        by_genre: dict[str, list[CorpusEntry]] = {}
        for e in entries:
            by_genre.setdefault(e.video.genre or "unknown", []).append(e)
        for genre in sorted(by_genre):
            rows = by_genre[genre]
            keep = sum(1 for e in rows if e.extractability.verdict is Verdict.KEEP)
            print(f"\n## {genre}  ({len(rows)} videos, {keep} keep)")
            for e in rows:
                print(_fmt_entry_line(e))
    else:
        print(f"# {len(entries)} entries")
        for e in entries:
            print(_fmt_entry_line(e))
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    store = _build_store(args.corpus_root)
    store.init_schema()
    entry = store.get(args.video_id)
    if entry is None:
        raise SystemExit(f"no corpus entry for {args.video_id}")

    if args.json:
        print(entry.model_dump_json(indent=2))
    else:
        v, s, x = entry.video, entry.snapshot, entry.extractability
        print(f"video_id     {v.video_id}")
        print(f"title        {v.title}")
        print(f"channel      {v.channel or '-'}")
        print(f"genre/stage  {v.genre or '-'} / {v.stage or '-'}")
        print(f"query_origin {v.query_origin or '-'}")
        print(f"caption_src  {s.caption_source.value}  ({s.segment_count} segments, {s.char_count} chars)")
        print(f"sha256       {s.content_sha256}")
        print(f"retrieved    {s.retrieval_date.isoformat()}")
        print(f"score        {x.score:.3f}  ->  {x.verdict.value}")
        print(
            f"  components  caption={x.caption_source_weight:.2f} density={x.word_density:.2f} "
            f"vocab={x.vocab_presence:.2f} actionable={x.actionable_ratio:.2f} "
            f"visual_penalty={x.visual_only_penalty:.2f}"
        )
        print(f"  flags       {', '.join(x.flags) if x.flags else '-'}")

    if args.segments > 0:
        snapshot = store.load_snapshot(args.video_id)
        if snapshot is not None:
            print(f"\n# first {args.segments} snapshot segments (video_id @ ts citation anchors)")
            for seg in snapshot.segments[: args.segments]:
                print(f"  [{seg.start_s:>7.2f}s] {seg.text}")
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    store = _build_store(args.corpus_root)
    store.init_schema()
    stats = store.stats()
    if args.json:
        print(stats.model_dump_json(indent=2))
        return 0
    print(f"total: {stats.total}")
    print(f"by_verdict:       {dict(sorted(stats.by_verdict.items()))}")
    print(f"by_genre:         {dict(sorted(stats.by_genre.items()))}")
    print(f"by_caption_source:{dict(sorted(stats.by_caption_source.items()))}")
    return 0


# ---------------------------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------------------------
def _add_common_run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT, help="corpus dir (registry.sqlite + snapshots/)")
    p.add_argument("--limit", type=int, default=5, help="results per discovery query (ytsearch fan-out)")
    p.add_argument("--genres", nargs="*", default=None, help=f"genres to search (default: {' '.join(GENRES)})")
    p.add_argument("--stages", nargs="*", default=None, help="production stages to search (default: all)")
    p.add_argument("--expand-synonyms", action="store_true", help="cross-product all phrasing synonyms (max recall)")
    p.add_argument(
        "--fixtures",
        nargs="?",
        const="",
        default=None,
        metavar="DIR",
        help="OFFLINE mode over a fixture corpus (default: bundled fixtures). Omit for live env-gated ingest.",
    )
    p.add_argument("--no-asr", action="store_true", help="disable the faster-whisper ASR fallback")
    p.add_argument("--min-interval", type=float, default=2.0, help="live throttle: min seconds between requests")
    p.add_argument("--jitter", type=float, default=0.5, help="live throttle: added random jitter (seconds)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corpus",
        description="Nameless tutorial-corpus ingestion (discover, snapshot, score, register).",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="build the grid + resolve candidate videos (no ingest)")
    _add_common_run_args(p_discover)
    p_discover.set_defaults(func=_handle_discover)

    p_ingest = sub.add_parser("ingest", help="discover -> fetch+fallback -> snapshot -> score -> register")
    _add_common_run_args(p_ingest)
    p_ingest.set_defaults(func=_handle_ingest)

    p_list = sub.add_parser("list", help="inspect the corpus registry")
    p_list.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    p_list.add_argument("--by-genre", action="store_true", help="group the listing by genre")
    p_list.add_argument("--by-extractability", action="store_true", help="order by extractability score (desc)")
    p_list.add_argument("--genre", default=None, help="filter to one genre")
    p_list.add_argument("--verdict", default=None, choices=[v.value for v in Verdict], help="filter by verdict")
    p_list.add_argument("--min-score", type=float, default=None, help="filter to score >= X")
    p_list.set_defaults(func=_handle_list)

    p_show = sub.add_parser("show", help="show one corpus entry (+ optional timestamped segments)")
    p_show.add_argument("video_id")
    p_show.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    p_show.add_argument("--segments", type=int, default=0, help="also print the first N snapshot segments")
    p_show.set_defaults(func=_handle_show)

    p_stats = sub.add_parser("stats", help="compact corpus roll-up (total / by verdict / by genre)")
    p_stats.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    p_stats.set_defaults(func=_handle_stats)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=os.environ.get("NAMELESS_LOG", "WARNING"))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
