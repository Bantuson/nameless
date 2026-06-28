"""``claims`` CLI — mine + inspect the cited-claim layer. Compact output by construction (token strategy).

Subcommands:
  * ``claims mine``    — extract -> verify citation -> dedup -> cross-reference -> persist. [KNOW-05/06]
  * ``claims list``    — inspect claims (``--by-stage`` / ``--by-genre``) or contested clusters
                         (``--conflicts``), with filters.
  * ``claims show``    — one claim traced to its source quote + timestamp + video. [KNOW-05 #2]
  * ``claims stats``   — compact roll-up (claims / clusters / contested / citation-verified).

Two run modes (live is the DEFAULT; pass ``--fixtures`` for the offline path):
  * live (no ``--fixtures``) — the REAL AnthropicClaimExtractor over the Phase-3 snapshot corpus.
    ENV-GATED: needs ``uv sync --extra extract`` + ``ANTHROPIC_API_KEY`` + real tokens (see README).
  * ``--fixtures [DIR]`` (DIR defaults to the bundled claim fixtures) — OFFLINE: a deterministic
    FakeClaimExtractor over the fixture transcripts + the REAL SqliteClaimStore (sqlite is stdlib). Runs
    anywhere on the base install; great for a demo/CI and the no-synthesis walkthrough.

Output stays compact: one terse line per claim/cluster; the verbatim quote is printed only by
``claims show`` (the trace-back), never dumped in a listing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .domain.claims import Claim, ClaimCluster
from .mining_pipeline import MineTarget, MiningConfig, MiningPipeline, MiningReport

DEFAULT_CORPUS_ROOT = os.path.join(".nameless-knowledge", "corpus")
KEEP_VERDICTS = ("keep", "low_signal")  # which corpus entries are worth mining


# ---------------------------------------------------------------------------------------------
# Plane construction
# ---------------------------------------------------------------------------------------------
def _claim_store(corpus_root: str):
    from .adapters.claim_store_sqlite import SqliteClaimStore

    return SqliteClaimStore(Path(corpus_root) / "registry.sqlite")


def _fixture_plane(args: argparse.Namespace):
    """Offline plane: in-memory corpus of fixture snapshots + FakeClaimExtractor + real sqlite store."""
    from .adapters import FakeClaimExtractor, InMemoryCorpusStore, KeywordSimilarityIndex, SystemClock
    from .claim_fixtures import DEFAULT_CLAIM_FIXTURE_DIR, load_claim_fixtures
    from .pure.snapshot import snapshot_record

    fixture_dir = args.fixtures or str(DEFAULT_CLAIM_FIXTURE_DIR)
    corpus_data = load_claim_fixtures(fixture_dir)

    mem_corpus = InMemoryCorpusStore()
    clock = SystemClock()
    for vid, transcript in corpus_data.transcripts.items():
        mem_corpus.write_snapshot(transcript, snapshot_record(transcript, clock.now()))

    extractor = FakeClaimExtractor(scripted=corpus_data.scripted)
    targets = [MineTarget(video_id=vid, genres=corpus_data.genres.get(vid, [])) for vid in corpus_data.video_ids]
    similarity = KeywordSimilarityIndex()
    return extractor, mem_corpus, similarity, targets


def _live_plane(args: argparse.Namespace):
    """Live plane (env-gated): Phase-3 filesystem corpus + AnthropicClaimExtractor."""
    if importlib.util.find_spec("anthropic") is None:
        raise SystemExit(
            "'anthropic' is not installed. Live mining is env-gated:\n"
            "  uv sync --extra extract\n"
            "(or run offline against fixtures with --fixtures). See README 'Verification'."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Live mining needs a key + tokens (env-gated).")

    from .adapters import KeywordSimilarityIndex
    from .adapters.claim_extractor_anthropic import AnthropicClaimExtractor
    from .adapters.corpus_fs import FilesystemCorpusStore

    corpus = FilesystemCorpusStore(args.corpus_root)
    corpus.init_schema()
    extractor = AnthropicClaimExtractor(model=args.model)

    if args.video:
        targets = [MineTarget(video_id=v, genres=[]) for v in args.video]
    else:
        targets = [
            MineTarget(video_id=e.video.video_id, genres=[e.video.genre] if e.video.genre else [])
            for e in corpus.list_entries()
            if e.extractability.verdict.value in KEEP_VERDICTS
        ]
    return extractor, corpus, KeywordSimilarityIndex(), targets


def _build_pipeline(args: argparse.Namespace):
    store = _claim_store(args.corpus_root)
    config = MiningConfig(require_citation=args.require_citation, semantic_dedup=args.semantic_dedup)
    if args.fixtures is not None:
        extractor, corpus, similarity, targets = _fixture_plane(args)
    else:
        extractor, corpus, similarity, targets = _live_plane(args)
    pipeline = MiningPipeline(extractor, store, corpus, similarity=similarity, config=config)
    return pipeline, targets


# ---------------------------------------------------------------------------------------------
# Compact formatting
# ---------------------------------------------------------------------------------------------
def _mmss(ms: int) -> str:
    mm, ss = divmod(ms // 1000, 60)
    return f"{mm:02d}:{ss:02d}"


def _fmt_claim_line(c: Claim) -> str:
    stance = c.stance or "-"
    return (
        f"{c.id}  {c.topic:<26}  conf={c.confidence:.2f}  "
        f"{c.source_video_id:<26}@{_mmss(c.timestamp_ms)}  stance={stance}"
    )


def _fmt_cluster_line(cl: ClaimCluster) -> str:
    kind = "CONFLICT" if cl.is_contested else "consensus"
    if cl.is_contested:
        sides = " vs ".join(sorted(cl.sides().keys()))
        detail = f"{len(cl.conflicts)} claims / {cl.distinct_conflict_sources} src  [{sides}]"
    else:
        detail = f"{len(cl.consensus)} claims / {cl.distinct_consensus_sources} distinct src"
    return f"{kind:<9}  {cl.topic:<28}  {detail}"


def _print_report(report: MiningReport, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json(indent=2))
        return
    print(
        f"claims={report.total_claims}  clusters={report.total_clusters}  "
        f"contested={report.contested_clusters}  duplicates_dropped={report.duplicates_dropped}"
    )
    for o in report.outcomes:
        print(f"  {o.video_id:<28}  extracted={o.extracted}  cited_ok={o.citations_ok}  "
              f"cited_fail={o.citations_failed}  kept={o.kept}  {o.detail}")


# ---------------------------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------------------------
def _handle_mine(args: argparse.Namespace) -> int:
    pipeline, targets = _build_pipeline(args)
    report = pipeline.mine(targets)
    _print_report(report, args.json)
    return 0


def _handle_list(args: argparse.Namespace) -> int:
    store = _claim_store(args.corpus_root)
    store.init_schema()

    if args.conflicts:
        clusters = store.list_clusters(contested_only=True, stage=args.stage, genre=args.genre)
        if args.json:
            print(json.dumps([cl.model_dump(mode="json") for cl in clusters], indent=2))
            return 0
        print(f"# {len(clusters)} contested clusters (both sides preserved)")
        for cl in clusters:
            print(_fmt_cluster_line(cl))
            for stance, claims in cl.sides().items():
                print(f"    [{stance}]  {len({c.source_video_id for c in claims})} src")
                for c in claims:
                    print(f"      {c.id}  {c.source_video_id}@{_mmss(c.timestamp_ms)}  conf={c.confidence:.2f}")
        return 0

    claims = store.list_claims(
        stage=args.stage, genre=args.genre, technique=args.technique,
        source_video_id=args.video, min_confidence=args.min_confidence,
    )
    if args.json:
        print(json.dumps([c.model_dump(mode="json") for c in claims], indent=2))
        return 0

    if args.by_stage:
        grouped: dict[str, list[Claim]] = {}
        for c in claims:
            grouped.setdefault(c.stage, []).append(c)
        for stage in sorted(grouped):
            print(f"\n## {stage}  ({len(grouped[stage])} claims)")
            for c in grouped[stage]:
                print(_fmt_claim_line(c))
    elif args.by_genre:
        grouped = {}
        for c in claims:
            for g in (c.genre or ["unknown"]):
                grouped.setdefault(g, []).append(c)
        for genre in sorted(grouped):
            print(f"\n## {genre}  ({len(grouped[genre])} claims)")
            for c in grouped[genre]:
                print(_fmt_claim_line(c))
    else:
        print(f"# {len(claims)} claims")
        for c in claims:
            print(_fmt_claim_line(c))
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    store = _claim_store(args.corpus_root)
    store.init_schema()
    claim = store.get_claim(args.claim_id)
    if claim is None:
        raise SystemExit(f"no claim {args.claim_id}")
    if args.json:
        print(claim.model_dump_json(indent=2))
        return 0
    print(f"id           {claim.id}")
    print(f"claim        {claim.claim_text}")
    print(f"technique    {claim.technique}   stage={claim.stage}   topic={claim.topic}")
    print(f"genre        {', '.join(claim.genre) or '-'}   stance={claim.stance or '-'}")
    print(f"confidence   {claim.confidence:.2f}   caption_source={claim.caption_source.value}")
    print(f"source       {claim.source_video_id} @ {_mmss(claim.timestamp_ms)} ({claim.timestamp_ms} ms)")
    print(f'quote        "{claim.quote}"')
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    store = _claim_store(args.corpus_root)
    store.init_schema()
    stats = store.stats()
    if args.json:
        print(stats.model_dump_json(indent=2))
        return 0
    print(f"total_claims:       {stats.total_claims}")
    print(f"total_clusters:     {stats.total_clusters}  (contested: {stats.contested_clusters})")
    print(f"citation_verified:  {stats.citation_verified}/{stats.total_claims}")
    print(f"by_stage:           {dict(sorted(stats.by_stage.items()))}")
    print(f"by_genre:           {dict(sorted(stats.by_genre.items()))}")
    print(f"by_caption_source:  {dict(sorted(stats.by_caption_source.items()))}")
    return 0


# ---------------------------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------------------------
def _add_corpus_root(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT, help="corpus dir (holds registry.sqlite)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claims",
        description="Nameless cited-claim mining + cross-reference (extraction only; no synthesis).",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_mine = sub.add_parser("mine", help="extract -> verify -> dedup -> cross-reference -> persist")
    _add_corpus_root(p_mine)
    p_mine.add_argument(
        "--fixtures", nargs="?", const="", default=None, metavar="DIR",
        help="run OFFLINE over the bundled claim fixtures (DIR optional). Omit this flag for the "
             "default live, env-gated mining path.",
    )
    p_mine.add_argument("--video", nargs="*", default=None, help="(live) specific video ids to mine")
    p_mine.add_argument("--model", default="claude-opus-4-8", help="(live) Claude model id")
    p_mine.add_argument(
        "--require-citation", action=argparse.BooleanOptionalAction, default=True,
        help="drop claims whose citation fails (default: on; use --no-require-citation to keep+flag them)",
    )
    p_mine.add_argument("--semantic-dedup", action="store_true", help="use the similarity index for same-source dedup")
    p_mine.set_defaults(func=_handle_mine)

    p_list = sub.add_parser("list", help="inspect claims, or contested clusters with --conflicts")
    _add_corpus_root(p_list)
    p_list.add_argument("--by-stage", action="store_true", help="group claims by production stage")
    p_list.add_argument("--by-genre", action="store_true", help="group claims by genre")
    p_list.add_argument("--conflicts", action="store_true", help="list contested clusters (both sides preserved)")
    p_list.add_argument("--stage", default=None)
    p_list.add_argument("--genre", default=None)
    p_list.add_argument("--technique", default=None)
    p_list.add_argument("--video", default=None, help="filter to one source video id")
    p_list.add_argument("--min-confidence", type=float, default=None)
    p_list.set_defaults(func=_handle_list)

    p_show = sub.add_parser("show", help="trace one claim to its source quote + timestamp + video")
    p_show.add_argument("claim_id")
    _add_corpus_root(p_show)
    p_show.set_defaults(func=_handle_show)

    p_stats = sub.add_parser("stats", help="compact roll-up (claims / clusters / contested / verified)")
    _add_corpus_root(p_stats)
    p_stats.set_defaults(func=_handle_stats)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=os.environ.get("NAMELESS_LOG", "WARNING"))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
