"""``nameless-workers`` CLI — the worker-plane surface, mirroring the ``nameless`` compact contract.

Subcommands:
  * ``fragments search --note "<text>"``      retrieve fragments whose audio matches a text query
  * ``fragments search --similar-to <id>``    retrieve fragments similar to a given fragment
  * ``analyze --fragment <id>``               run feature-extraction for one fragment (single-shot;
                                              this is how the Rust sqlxmq runner invokes Python)
  * ``run [--once]``                          poll the job source and analyze jobs as they arrive

Output is COMPACT by construction (PRD §12): search prints ``id  key  tempo  score`` (or a JSON array
of the same), never a vector or a feature array. ``--json`` switches to machine output.

Heavy adapters (Postgres, CLAP, librosa) are imported lazily inside the plane builders, so ``--help``
and argument parsing work with only the light base install; the real backends are env-gated:
  * ``DATABASE_URL``         — Postgres DSN (required for any command that touches the repo)
  * ``NAMELESS_OBJECT_ROOT`` — content-addressed audio dir (default ``.nameless-local/objects``)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional
from uuid import UUID

from .domain.models import AnalyzeOutcome, FeatureExtractJob, SearchHit
from .ports import SearchField, SearchQuery


# ---------------------------------------------------------------------------------------------
# Plane construction (lazy, env-gated)
# ---------------------------------------------------------------------------------------------
def _require_database_url() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required (Postgres DSN) for this command")
    return dsn


def _build_repo():
    from .adapters.repo_pg import PgFragmentRepo

    return PgFragmentRepo(_require_database_url())


def _build_embedder():
    from .adapters.embed_clap import ClapEmbedder

    return ClapEmbedder()


def _build_loader():
    root = os.environ.get("NAMELESS_OBJECT_ROOT", os.path.join(".nameless-local", "objects"))
    from .adapters.audio_loader_store import FilesystemAudioLoader

    return FilesystemAudioLoader(root)


def _build_extractor():
    from .adapters.feature_librosa import LibrosaFeatureExtractor

    return LibrosaFeatureExtractor()


# ---------------------------------------------------------------------------------------------
# Output (compact chokepoint — cannot emit vectors/arrays)
# ---------------------------------------------------------------------------------------------
def _print_hits(hits: list[SearchHit], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "fragment_id": str(h.fragment_id),
                        "key": h.key,
                        "tempo_bpm": h.tempo_bpm,
                        "score": round(h.score, 6),
                    }
                    for h in hits
                ]
            )
        )
        return
    for h in hits:
        key = h.key if h.key is not None else "-"
        tempo = f"{h.tempo_bpm:.1f}" if h.tempo_bpm is not None else "-"
        print(f"{h.fragment_id}  {key:<7}  {tempo:>6}  {h.score:.4f}")


def _print_outcome(outcome: AnalyzeOutcome, as_json: bool) -> None:
    if as_json:
        print(outcome.model_dump_json())
        return
    if outcome.skipped:
        print(f"{outcome.fragment_id}  already analyzed (skipped)")
        return
    key = outcome.key or "-"
    tempo = f"{outcome.tempo_bpm:.1f}" if outcome.tempo_bpm is not None else "-"
    lufs = f"{outcome.loudness_lufs:.1f}" if outcome.loudness_lufs is not None else "-"
    print(
        f"{outcome.fragment_id}  {outcome.from_state}→{outcome.to_state}  "
        f"key={key} tempo={tempo} lufs={lufs}"
    )


# ---------------------------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------------------------
def _handle_search(args: argparse.Namespace) -> int:
    field = SearchField(args.field)
    repo = _build_repo()

    project_id = UUID(args.project) if args.project else None

    if args.note is not None:
        # Embed the text query with the CLAP text tower; rank against the chosen field (default the
        # AUDIO column — the cross-modal "find audio that matches this description" retrieval).
        embedder = _build_embedder()
        query_vec = embedder.embed_text(args.note).vector
        query = SearchQuery(
            vector=query_vec,
            field=field,
            limit=args.limit,
            project_id=project_id,
        )
    else:
        # --similar-to: use the named fragment's own stored vector as the query, excluding itself.
        target_id = UUID(args.similar_to)
        query_vec = repo.get_embedding(target_id, field)
        if query_vec is None:
            raise SystemExit(f"fragment {target_id} has no {field.value} embedding (not analyzed yet)")
        query = SearchQuery(
            vector=query_vec,
            field=field,
            limit=args.limit,
            project_id=project_id,
            exclude_fragment_id=target_id,
        )

    hits = repo.search(query)
    _print_hits(hits, args.json)
    return 0


def _handle_analyze(args: argparse.Namespace) -> int:
    from .consumer import AnalyzeJobConsumer

    consumer = AnalyzeJobConsumer(
        loader=_build_loader(),
        extractor=_build_extractor(),
        embedder=_build_embedder(),
        repo=_build_repo(),
    )
    job = FeatureExtractJob(fragment_id=UUID(args.fragment))
    outcome = consumer.handle(job)
    _print_outcome(outcome, args.json)
    return 0


def _handle_run(args: argparse.Namespace) -> int:
    raise SystemExit(
        "`run` requires a JobSource binding (Rust sqlxmq runner → analyze, or a Postgres "
        "SKIP-LOCKED poller). See workers/README.md 'Running the worker'. Use `analyze --fragment "
        "<id>` for the single-shot path the control plane invokes."
    )


# ---------------------------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nameless-workers",
        description="Nameless audio-ML worker plane (feature extraction + CLAP retrieval).",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    # fragments search …
    p_frag = sub.add_parser("fragments", help="query the fragment graph")
    frag_sub = p_frag.add_subparsers(dest="frag_command", required=True)
    p_search = frag_sub.add_parser("search", help="retrieve fragments by note text or audio similarity")
    group = p_search.add_mutually_exclusive_group(required=True)
    group.add_argument("--note", type=str, help="text query (embedded with the CLAP text tower)")
    group.add_argument("--similar-to", type=str, metavar="FRAGMENT_ID", help="a fragment UUID")
    p_search.add_argument(
        "--field",
        choices=[f.value for f in SearchField],
        default=SearchField.AUDIO.value,
        help="which joint-space column to rank against (default: audio)",
    )
    p_search.add_argument("--project", type=str, default=None, help="restrict to a project UUID")
    p_search.add_argument("--limit", type=int, default=10, help="max results (default 10)")
    p_search.set_defaults(func=_handle_search)

    # analyze --fragment <id>
    p_analyze = sub.add_parser("analyze", help="run feature extraction for one fragment (single-shot)")
    p_analyze.add_argument("--fragment", type=str, required=True, metavar="FRAGMENT_ID")
    p_analyze.set_defaults(func=_handle_analyze)

    # run [--once]
    p_run = sub.add_parser("run", help="poll the job source and analyze jobs")
    p_run.add_argument("--once", action="store_true", help="process at most one job and exit")
    p_run.add_argument("--max-idle", type=int, default=None, help="stop after N consecutive empty polls")
    p_run.set_defaults(func=_handle_run)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=os.environ.get("NAMELESS_LOG", "INFO"))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
