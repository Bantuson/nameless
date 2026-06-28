"""``skills`` CLI — synthesize + audit the authored production skills. Compact output by construction.

Subcommands:
  * ``skills synthesize`` — select P1 cells -> synthesize -> GATE -> emit draft SKILL.md files. [KNOW-07/08/09]
  * ``skills ground``     — author an UNDER-tutorialized skill (alt-piano) by decomposition + audio analysis,
                            stamped LOW confidence, behind the SAME gate. [KNOW-10]
  * ``skills list``       — inspect authored skills (``--by-genre`` / ``--by-stage`` / ``--status``).
  * ``skills show``       — one skill: frontmatter + audit roll-up + (optional) the SKILL.md body. [KNOW-09]
  * ``skills audit``      — sample a set with citation coverage + flags (the human spot-audit). [KNOW-11]
  * ``skills promote``    — flip a skill draft -> promoted. HUMAN-GATED: requires ``--yes`` after review. [KNOW-11]
  * ``skills stats``      — compact roll-up (total / draft / promoted / by confidence).

Two run modes for ``synthesize``:
  * ``--fixtures [DIR]`` (default = bundled claim fixtures) — OFFLINE end-to-end: mine the fixtures into an
    in-memory claim layer (Phase-4 fakes), synthesize with the deterministic FakeSkillSynthesizer, GATE,
    and write REAL SKILL.md files + a REAL ``registry.sqlite`` (sqlite is stdlib). Runs anywhere on the
    base install — this is what produces the committed example skills with no API call.
  * live (no ``--fixtures``) — read the Phase-4 ``claims``/``clusters`` from ``registry.sqlite`` and author
    with the REAL AnthropicSkillSynthesizer. ENV-GATED: ``uv sync --extra extract`` + ``ANTHROPIC_API_KEY``.

Output stays compact (token strategy): one terse line per skill/cell; the SKILL.md body is printed only by
``skills show --body``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Optional

from .domain.skills import AuthoredSkill, SkillStatus
from .pure.audit import audit_sample, coverage
from .synthesis_pipeline import SynthesisConfig, SynthesisPipeline, SynthesisReport

DEFAULT_CORPUS_ROOT = os.path.join(".nameless-knowledge", "corpus")
DEFAULT_SKILLS_ROOT = "."  # SKILL.md files land under <root>/skills/production/<stage>/<genre>/


# ---------------------------------------------------------------------------------------------
# Plane construction
# ---------------------------------------------------------------------------------------------
def _skill_store(args: argparse.Namespace):
    from .adapters.skill_store_fs import FilesystemSkillStore

    db = Path(args.corpus_root) / "registry.sqlite"
    store = FilesystemSkillStore(db, args.skills_root)
    store.init_schema()
    return store


def _fixture_plane(args: argparse.Namespace):
    """Offline plane: mine the claim fixtures (Phase-4 fakes) -> fake synthesizer -> real fs skill store."""
    from .adapters import (
        FakeClaimExtractor,
        FakeSkillSynthesizer,
        InMemoryClaimStore,
        InMemoryCorpusStore,
        KeywordSimilarityIndex,
        SystemClock,
    )
    from .adapters.skill_store_fs import FilesystemSkillStore
    from .claim_fixtures import DEFAULT_CLAIM_FIXTURE_DIR, load_claim_fixtures
    from .mining_pipeline import MineTarget, MiningPipeline
    from .pure.snapshot import snapshot_record

    fixture_dir = args.fixtures or str(DEFAULT_CLAIM_FIXTURE_DIR)
    corpus_data = load_claim_fixtures(fixture_dir)

    corpus = InMemoryCorpusStore()
    clock = SystemClock()
    for vid, transcript in corpus_data.transcripts.items():
        corpus.write_snapshot(transcript, snapshot_record(transcript, clock.now()))

    claim_store = InMemoryClaimStore()
    MiningPipeline(
        FakeClaimExtractor(scripted=corpus_data.scripted),
        claim_store,
        corpus,
        similarity=KeywordSimilarityIndex(),
    ).mine([MineTarget(video_id=v, genres=corpus_data.genres.get(v, [])) for v in corpus_data.video_ids])

    synthesizer = FakeSkillSynthesizer()
    db = Path(args.corpus_root) / "registry.sqlite"
    skill_store = FilesystemSkillStore(db, args.skills_root)
    return synthesizer, skill_store, claim_store, corpus


def _live_plane(args: argparse.Namespace):
    """Live plane (env-gated): Phase-4 sqlite claim layer + AnthropicSkillSynthesizer."""
    if importlib.util.find_spec("anthropic") is None:
        raise SystemExit(
            "'anthropic' is not installed. Live synthesis is env-gated:\n"
            "  uv sync --extra extract\n"
            "(or run offline against fixtures with --fixtures). See README 'Verification'."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Live synthesis needs a key + tokens (env-gated).")

    from .adapters.claim_store_sqlite import SqliteClaimStore
    from .adapters.corpus_fs import FilesystemCorpusStore
    from .adapters.skill_store_fs import FilesystemSkillStore
    from .adapters.skill_synthesizer_anthropic import AnthropicSkillSynthesizer

    db = Path(args.corpus_root) / "registry.sqlite"
    corpus = FilesystemCorpusStore(args.corpus_root)
    corpus.init_schema()
    claim_store = SqliteClaimStore(db)
    claim_store.init_schema()
    synthesizer = AnthropicSkillSynthesizer(model=args.model)
    skill_store = FilesystemSkillStore(db, args.skills_root)
    return synthesizer, skill_store, claim_store, corpus


def _build_pipeline(args: argparse.Namespace) -> SynthesisPipeline:
    if args.fixtures is not None:
        synthesizer, skill_store, claim_store, corpus = _fixture_plane(args)
    else:
        synthesizer, skill_store, claim_store, corpus = _live_plane(args)
    config = SynthesisConfig(p1_only=not args.all)
    return SynthesisPipeline(synthesizer, skill_store, claim_store, corpus=corpus, config=config)


# ---------------------------------------------------------------------------------------------
# Phase-6 grounding plane construction (KNOW-10)
# ---------------------------------------------------------------------------------------------
def _grounding_fixture_plane(args: argparse.Namespace):
    """Offline plane: mine parent fixtures (Phase-4 fakes) + canned audio records -> real fs skill store."""
    from .adapters import (
        FakeClaimExtractor,
        FakeSkillSynthesizer,
        FakeTrackAnalyzer,
        InMemoryClaimStore,
        InMemoryCorpusStore,
        KeywordSimilarityIndex,
        SystemClock,
    )
    from .adapters.skill_store_fs import FilesystemSkillStore
    from .grounding_fixtures import load_grounding_fixtures
    from .mining_pipeline import MineTarget, MiningPipeline
    from .pure.snapshot import snapshot_record

    fx = load_grounding_fixtures()
    corpus = InMemoryCorpusStore()
    clock = SystemClock()
    for vid, transcript in fx.parents.transcripts.items():
        corpus.write_snapshot(transcript, snapshot_record(transcript, clock.now()))

    claim_store = InMemoryClaimStore()
    MiningPipeline(
        FakeClaimExtractor(scripted=fx.parents.scripted), claim_store, corpus,
        similarity=KeywordSimilarityIndex(),
    ).mine([MineTarget(video_id=v, genres=fx.parents.genres.get(v, [])) for v in fx.parents.video_ids])

    synthesizer = FakeSkillSynthesizer()
    analyzer = FakeTrackAnalyzer(fx.records)
    db = Path(args.corpus_root) / "registry.sqlite"
    skill_store = FilesystemSkillStore(db, args.skills_root)
    return synthesizer, skill_store, claim_store, analyzer, fx.tracks, corpus


def _grounding_live_plane(args: argparse.Namespace):
    """Live plane (env-gated): sqlite parent claims + WorkerTrackAnalyzer over real audio files."""
    if importlib.util.find_spec("nameless_workers") is None:
        raise SystemExit(
            "'nameless_workers' is not importable. Live grounding reuses the Phase-2 audio plane:\n"
            "  uv pip install -e workers[ml] -e knowledge-pipeline\n"
            "(or run offline against fixtures with --fixtures). See README 'Verification'."
        )
    if not args.tracks_dir:
        raise SystemExit("live grounding needs --tracks-dir <dir of released-track audio files>.")

    from .adapters.claim_store_sqlite import SqliteClaimStore
    from .adapters.corpus_fs import FilesystemCorpusStore
    from .adapters.skill_store_fs import FilesystemSkillStore
    from .adapters.skill_synthesizer_anthropic import AnthropicSkillSynthesizer
    from .adapters.track_analyzer_worker import WorkerTrackAnalyzer
    from .domain.grounding import TrackRef

    tracks_dir = Path(args.tracks_dir)
    tracks = [
        TrackRef(track_id=p.stem, artist=p.stem.replace("_", " ").title(), genre="alt-piano", audio_uri=str(p))
        for p in sorted(tracks_dir.glob("*"))
        if p.suffix.lower() in {".wav", ".flac", ".mp3", ".m4a", ".ogg"}
    ]
    db = Path(args.corpus_root) / "registry.sqlite"
    corpus = FilesystemCorpusStore(args.corpus_root)
    corpus.init_schema()
    claim_store = SqliteClaimStore(db)
    claim_store.init_schema()
    synthesizer = AnthropicSkillSynthesizer(model=args.model) if args.real_synth else None
    if synthesizer is None:
        from .adapters import FakeSkillSynthesizer  # default: deterministic synth over the live claim set
        synthesizer = FakeSkillSynthesizer()
    skill_store = FilesystemSkillStore(db, args.skills_root)
    return synthesizer, skill_store, claim_store, WorkerTrackAnalyzer(device=args.device), tracks, corpus


def _build_grounding_pipeline(args: argparse.Namespace):
    from .grounding_pipeline import GroundingConfig, GroundingPipeline

    if args.fixtures is not None:
        synthesizer, skill_store, claim_store, analyzer, tracks, corpus = _grounding_fixture_plane(args)
    else:
        synthesizer, skill_store, claim_store, analyzer, tracks, corpus = _grounding_live_plane(args)
    return GroundingPipeline(
        synthesizer, skill_store, claim_store, analyzer, tracks,
        corpus=corpus, config=GroundingConfig(),
    )


# ---------------------------------------------------------------------------------------------
# Compact formatting
# ---------------------------------------------------------------------------------------------
def _fmt_skill_line(s: AuthoredSkill) -> str:
    return (
        f"{s.id}  {s.slug:<24}  {s.status.value:<9}  conf={s.confidence_tier:<4}  "
        f"cites={s.citation_count:<2}  src={s.distinct_sources}  "
        f"{'contested' if s.default_contested else 'consensus'}"
    )


def _print_report(report: SynthesisReport, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json(indent=2))
        return
    print(f"authored={report.authored}  rejected={report.rejected}  total_cells={report.total_cells}")
    for o in report.outcomes:
        if o.status == "authored":
            print(f"  {o.cell:<24}  authored  {o.skill_id}  conf={o.confidence}  cites={o.citation_count}")
        else:
            print(f"  {o.cell:<24}  REJECTED  {'; '.join(o.reasons)}")


# ---------------------------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------------------------
def _handle_synthesize(args: argparse.Namespace) -> int:
    pipeline = _build_pipeline(args)
    report = pipeline.synthesize()
    _print_report(report, args.json)
    return 0


def _handle_ground(args: argparse.Namespace) -> int:
    from .domain.genres import canonical_genre
    from .pure.decompose import ALT_PIANO_TARGET, decompose, known_targets

    pipeline = _build_grounding_pipeline(args)
    target = ALT_PIANO_TARGET
    if args.target:
        # IN-03: accept the `alt-piano` alias for the `alternative-piano` cell (the slug used throughout
        # fixtures/records) via the centralized alias map, not just the literal cell genre/slug.
        wanted = canonical_genre(args.target)
        match = next(
            (t for t in known_targets()
             if canonical_genre(t.genre) == wanted or t.slug == args.target),
            None,
        )
        if match is None:
            raise SystemExit(
                f"no decomposition for target '{args.target}'. Known: "
                f"{', '.join(t.genre for t in known_targets())}"
            )
        target = match
    outcome = pipeline.ground(target)
    if args.json:
        print(outcome.model_dump_json(indent=2))
        return 0
    decomp = decompose(target)
    print(f"target={outcome.target}  status={outcome.status}  confidence={outcome.confidence or '-'}")
    print(f"decomposed into: {', '.join(p.label for p in decomp.parents)}")
    print(f"tutorial_sources={outcome.tutorial_sources}  audio_tracks={outcome.audio_tracks}  "
          f"cites={outcome.citation_count}  src={outcome.distinct_sources}")
    if outcome.status == "authored":
        print(f"authored {outcome.skill_id}  ({target.relpath})  [LOW — grounded, not direct tutorials]")
    else:
        print(f"REJECTED: {'; '.join(outcome.reasons)}")
    return 0 if outcome.status == "authored" else 1


def _handle_list(args: argparse.Namespace) -> int:
    store = _skill_store(args)
    status = SkillStatus(args.status) if args.status else None
    skills = store.list_skills(stage=args.stage, genre=args.genre, status=status)
    if args.json:
        print(json.dumps([s.model_dump(mode="json", exclude={"body_md"}) for s in skills], indent=2))
        return 0
    if args.by_genre or args.by_stage:
        key = (lambda s: s.genre) if args.by_genre else (lambda s: s.stage)
        grouped: dict[str, list[AuthoredSkill]] = {}
        for s in skills:
            grouped.setdefault(key(s), []).append(s)
        for g in sorted(grouped):
            print(f"\n## {g}  ({len(grouped[g])} skills)")
            for s in grouped[g]:
                print(_fmt_skill_line(s))
    else:
        print(f"# {len(skills)} authored skills")
        for s in skills:
            print(_fmt_skill_line(s))
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    store = _skill_store(args)
    skill = store.get_skill(args.skill_id)
    if skill is None:
        raise SystemExit(f"no skill {args.skill_id}")
    if args.json:
        print(skill.model_dump_json(indent=2, exclude={"body_md"} if not args.body else set()))
        return 0
    cov = coverage(skill)
    print(f"id           {skill.id}")
    print(f"name         {skill.name}")
    print(f"cell         {skill.genre} / {skill.stage}")
    print(f"status       {skill.status.value}")
    print(f"path         {skill.relpath}")
    print(f"confidence   {skill.confidence_tier}  (default backed by {skill.default_source_count} src, "
          f"contested={skill.default_contested})")
    print(f"citations    {skill.citation_count}  across {skill.distinct_sources} source(s)")
    print(f"topics       consensus={skill.consensus_topics}  conflict={skill.conflict_topics}")
    print(f"flags        {', '.join(cov.flags) if cov.flags else '-'}")
    print(f"prompt_ver   {skill.prompt_version}")
    if args.body:
        print("\n" + "-" * 80)
        print(skill.body_md)
    return 0


def _handle_audit(args: argparse.Namespace) -> int:
    store = _skill_store(args)
    skills = store.list_skills()
    report = audit_sample(
        skills, sample_size=args.sample, rng=random.Random(args.seed), drafts_only=not args.include_promoted
    )
    if args.json:
        print(json.dumps(
            {
                "total_skills": report.total_skills, "draft": report.draft, "promoted": report.promoted,
                "sample_size": report.sample_size, "flagged": report.flagged,
                "sampled": [c.__dict__ for c in report.sampled],
            },
            indent=2, default=lambda o: list(o) if isinstance(o, tuple) else o,
        ))
        return 0
    print(f"total={report.total_skills}  draft={report.draft}  promoted={report.promoted}  "
          f"sample={report.sample_size}  flagged={report.flagged}")
    print(f"# human spot-audit sample (seed={args.seed}) -- review each against its source quotes, then "
          f"`skills promote <id> --yes`")
    for c in report.sampled:
        flags = ", ".join(c.flags) if c.flags else "clean"
        print(f"  {c.skill_id}  {c.slug:<24}  conf={c.confidence_tier:<4}  cites={c.citation_count:<2}  "
              f"src={c.distinct_sources}  [{flags}]")
    return 0


def _handle_promote(args: argparse.Namespace) -> int:
    store = _skill_store(args)
    skill = store.get_skill(args.skill_id)
    if skill is None:
        raise SystemExit(f"no skill {args.skill_id}")
    if skill.status is SkillStatus.PROMOTED:
        print(f"{skill.id} ({skill.slug}) is already promoted.")
        return 0

    cov = coverage(skill)
    # The human gate: show what is being promoted; require an explicit --yes to actually flip status.
    print(f"skill   {skill.id}  {skill.slug}")
    print(f"conf    {skill.confidence_tier}  cites={skill.citation_count}  src={skill.distinct_sources}")
    print(f"flags   {', '.join(cov.flags) if cov.flags else '-'}")
    if not args.yes:
        print("NOT promoted. This is human-gated: review the SKILL.md against its source quotes "
              "(`skills show <id> --body`), then re-run with --yes to promote.")
        return 0
    updated = store.set_status(skill.id, SkillStatus.PROMOTED)
    assert updated is not None
    print(f"PROMOTED {updated.id} ({updated.slug}) -> {updated.status.value}")
    return 0


def _handle_stats(args: argparse.Namespace) -> int:
    store = _skill_store(args)
    stats = store.stats()
    if args.json:
        print(stats.model_dump_json(indent=2))
        return 0
    print(f"total_skills:   {stats.total_skills}  (draft: {stats.draft}, promoted: {stats.promoted})")
    print(f"by_genre:       {dict(sorted(stats.by_genre.items()))}")
    print(f"by_stage:       {dict(sorted(stats.by_stage.items()))}")
    print(f"by_confidence:  {dict(sorted(stats.by_confidence.items()))}")
    return 0


# ---------------------------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------------------------
def _add_roots(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT, help="dir holding registry.sqlite")
    p.add_argument("--skills-root", default=DEFAULT_SKILLS_ROOT,
                   help="base dir for SKILL.md files (writes <root>/skills/production/<stage>/<genre>/)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skills",
        description="Nameless skill synthesis + citation gate + human spot-audit (synthesize only over claims).",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_syn = sub.add_parser("synthesize", help="select P1 cells -> synthesize -> GATE -> emit draft SKILL.md")
    _add_roots(p_syn)
    p_syn.add_argument(
        "--fixtures", nargs="?", const="", default=None, metavar="DIR",
        help="OFFLINE end-to-end over the bundled claim fixtures (default). Omit for live env-gated synthesis.",
    )
    p_syn.add_argument("--all", action="store_true", help="author ALL evidenced cells, not only the P1 grid")
    p_syn.add_argument("--model", default="claude-opus-4-8", help="(live) Claude model id")
    p_syn.set_defaults(func=_handle_synthesize)

    p_grd = sub.add_parser(
        "ground",
        help="author an UNDER-tutorialized skill (alt-piano) by decomposition + audio analysis (KNOW-10)",
    )
    _add_roots(p_grd)
    p_grd.add_argument(
        "--fixtures", nargs="?", const="", default=None, metavar="DIR",
        help="OFFLINE end-to-end over the bundled parent claim + audio-record fixtures (default). "
             "Omit for live env-gated grounding (reuses the workers audio plane).",
    )
    p_grd.add_argument("--target", default=None,
                       help="target subgenre to ground (default: alternative-piano)")
    p_grd.add_argument("--tracks-dir", default=None,
                       help="(live) directory of released-track audio files to analyze")
    p_grd.add_argument("--device", default="cpu", help="(live) torch device for the workers analyzer")
    p_grd.add_argument("--real-synth", action="store_true",
                       help="(live) use the Anthropic synthesizer instead of the deterministic template")
    p_grd.add_argument("--model", default="claude-opus-4-8", help="(live) Claude model id")
    p_grd.set_defaults(func=_handle_ground)

    p_list = sub.add_parser("list", help="inspect authored skills")
    _add_roots(p_list)
    p_list.add_argument("--by-genre", action="store_true")
    p_list.add_argument("--by-stage", action="store_true")
    p_list.add_argument("--stage", default=None)
    p_list.add_argument("--genre", default=None)
    p_list.add_argument("--status", default=None, choices=[s.value for s in SkillStatus])
    p_list.set_defaults(func=_handle_list)

    p_show = sub.add_parser("show", help="show one skill (frontmatter + audit roll-up; --body for the SKILL.md)")
    p_show.add_argument("skill_id")
    _add_roots(p_show)
    p_show.add_argument("--body", action="store_true", help="also print the full SKILL.md body")
    p_show.set_defaults(func=_handle_show)

    p_audit = sub.add_parser("audit", help="sample skills with citation coverage + flags (human spot-audit)")
    _add_roots(p_audit)
    p_audit.add_argument("--sample", type=int, default=3, help="how many skills to surface for review")
    p_audit.add_argument("--seed", type=int, default=0, help="seed for a reproducible sample")
    p_audit.add_argument("--include-promoted", action="store_true", help="also sample already-promoted skills")
    p_audit.set_defaults(func=_handle_audit)

    p_prom = sub.add_parser("promote", help="promote a draft skill (HUMAN-GATED: requires --yes after review)")
    p_prom.add_argument("skill_id")
    _add_roots(p_prom)
    p_prom.add_argument("--yes", action="store_true", help="confirm promotion after auditing the skill")
    p_prom.set_defaults(func=_handle_promote)

    p_stats = sub.add_parser("stats", help="compact roll-up (total / draft / promoted / by confidence)")
    _add_roots(p_stats)
    p_stats.set_defaults(func=_handle_stats)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=os.environ.get("NAMELESS_LOG", "WARNING"))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
