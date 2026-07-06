"""FileSkillSynthesizer tests — the no-API synthesis path over pre-drafted ``{stage}__{genre}.json`` files.

Three layers, all offline (fakes/tmpdir/sqlite only — no network, no anthropic, no API key):

  * adapter unit tests   — contract parity with ``parse_synthesizer_output`` (identical normalization to
    the Anthropic adapter's return path), precise error types for missing/malformed/unusable files, the
    collision-safe ``{stage}__{genre}.json`` naming convention, and NO template fallback (nothing the
    human never drafted may be authored).
  * gate parity          — a parseable draft citing REAL claims but asserting an invented number is
    RETURNED by the adapter and then REJECTED by the UNCHANGED pure ``citation_gate`` — file drafts get
    no special pass, exactly like API output.
  * scoping seam         — ``scope_clusters_to_cells`` / ``CellScopedClaimStore`` make missing-file cells
    never selected (the skip seam) while keeping available cells' cluster membership + the gate's claim
    index byte-identical to an unscoped run.
  * CLI e2e (Task 2)     — ``skills synthesize --drafts-dir`` against the REAL FilesystemCorpusStore +
    REAL SqliteClaimStore + REAL FilesystemSkillStore with no ANTHROPIC_API_KEY set.
"""

from __future__ import annotations

import json

import pytest

from knowledge_pipeline.adapters.skill_synthesizer_file import (
    FILE_DRAFT_PROMPT_VERSION,
    CellScopedClaimStore,
    DraftFileError,
    FileSkillSynthesizer,
    draft_filename,
    scope_clusters_to_cells,
)
from knowledge_pipeline.domain.skills import ProductionCell, SkillDraft
from knowledge_pipeline.pure.cell_selection import clusters_for_cell, select_cells
from knowledge_pipeline.pure.citation_gate import citation_gate
from knowledge_pipeline.pure.synthesis_schema import parse_synthesizer_output
from knowledge_pipeline.pure.synthesis_template import template_synthesize

from .conftest import mine_fixture_claim_layer

# ---------------------------------------------------------------------------------------------
# Payload helpers — the file body IS the `emit_skill` tool input (EMIT_SKILL_TOOL_SCHEMA shape).
# ---------------------------------------------------------------------------------------------


def _draft_to_payload(draft: SkillDraft) -> dict:
    """Invert a SkillDraft into the ``emit_skill`` tool-input dict (citations as id references only)."""
    return {
        "name": draft.name,
        "description": draft.description,
        "default": {
            "body": draft.default.body,
            "claim_ids": [c.claim_id for c in draft.default.citations],
            "stance": draft.default.stance,
        },
        "sections": [
            {
                "kind": s.kind.value,
                "topic": s.topic,
                "technique": s.technique,
                "stance": s.stance,
                "body": s.body,
                "claim_ids": [c.claim_id for c in s.citations],
            }
            for s in draft.sections
        ],
    }


@pytest.fixture
def fixture_layer():
    """``(claim_store, corpus, snapshots, clusters, cells)`` — the mined fixture claim layer + selection."""
    claim_store, corpus, snapshots = mine_fixture_claim_layer()
    clusters = claim_store.list_clusters()
    cells = select_cells(clusters)
    return claim_store, corpus, snapshots, clusters, cells


def _write_draft(tmp_path, cell, payload: dict) -> None:
    (tmp_path / draft_filename(cell)).write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Naming convention
# ---------------------------------------------------------------------------------------------


def test_draft_filename_convention():
    cell = ProductionCell(stage="drums", genre="deep-house")
    assert draft_filename(cell) == "drums__deep-house.json"
    assert draft_filename(ProductionCell(stage="vocal-layering", genre="rnb")) == "vocal-layering__rnb.json"
    assert draft_filename(ProductionCell(stage="bassline", genre="deep-house")) == "bassline__deep-house.json"


def test_draft_filename_is_collision_safe_across_hyphenated_labels():
    # normalize_key emits only [a-z0-9-], so the "__" separator can never occur inside a token —
    # ("drums", "deep-house") and ("drums-deep", "house") must map to DIFFERENT filenames.
    a = draft_filename(ProductionCell(stage="drums", genre="deep-house"))
    b = draft_filename(ProductionCell(stage="drums-deep", genre="house"))
    assert a == "drums__deep-house.json"
    assert b == "drums-deep__house.json"
    assert a != b


# ---------------------------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------------------------


def test_happy_path_matches_parse_synthesizer_output(tmp_path, fixture_layer):
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    cell = cells[0]
    cell_clusters = clusters_for_cell(clusters, cell)
    payload = _draft_to_payload(template_synthesize(cell, cell_clusters))
    _write_draft(tmp_path, cell, payload)

    synth = FileSkillSynthesizer(tmp_path)
    draft = synth.synthesize(cell, cell_clusters)

    # Contract parity: byte-for-byte the same normalization/re-grounding as parse_synthesizer_output.
    expected = parse_synthesizer_output(
        payload, cell, cell_clusters, prompt_version=FILE_DRAFT_PROMPT_VERSION
    )
    assert expected is not None
    assert draft.cited_claim_ids == expected.cited_claim_ids
    assert draft.default.body == expected.default.body
    assert [s.topic for s in draft.sections] == [s.topic for s in expected.sections]
    assert draft.prompt_version == FILE_DRAFT_PROMPT_VERSION
    assert synth.calls == [cell.slug]


def test_gate_rejects_a_file_draft_with_an_invented_number(tmp_path, fixture_layer):
    # THE core requirement: a draft citing REAL claims but asserting a fabricated parameter is
    # structurally valid (the adapter RETURNS it) — and the UNCHANGED citation_gate REJECTS it with
    # invented_number, exactly the treatment API output gets (mirrors InventingSynth expectations).
    claim_store, _corpus, snapshots, clusters, cells = fixture_layer
    cell = cells[0]
    cell_clusters = clusters_for_cell(clusters, cell)
    payload = _draft_to_payload(template_synthesize(cell, cell_clusters))
    payload["default"]["body"] += " Boost 999 Hz heavily."
    _write_draft(tmp_path, cell, payload)

    draft = FileSkillSynthesizer(tmp_path).synthesize(cell, cell_clusters)

    claim_index = {c.id: c for c in claim_store.list_claims()}
    result = citation_gate(draft, claim_index, snapshots=snapshots)
    assert not result.ok
    assert "invented_number" in result.codes


def test_missing_file_raises_filenotfound_naming_cell_and_path(tmp_path, fixture_layer):
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    cell = cells[0]
    cell_clusters = clusters_for_cell(clusters, cell)

    with pytest.raises(FileNotFoundError) as exc_info:
        FileSkillSynthesizer(tmp_path).synthesize(cell, cell_clusters)
    msg = str(exc_info.value)
    assert cell.slug in msg
    assert str(tmp_path / draft_filename(cell)) in msg


def test_malformed_json_raises_draftfileerror_naming_file(tmp_path, fixture_layer):
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    cell = cells[0]
    (tmp_path / draft_filename(cell)).write_text("{not valid json!!", encoding="utf-8")

    with pytest.raises(DraftFileError) as exc_info:
        FileSkillSynthesizer(tmp_path).synthesize(cell, clusters_for_cell(clusters, cell))
    assert str(tmp_path / draft_filename(cell)) in str(exc_info.value)


def test_wrong_top_level_type_raises_draftfileerror(tmp_path, fixture_layer):
    # A bare array is valid JSON but NOT the emit_skill tool-input shape.
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    cell = cells[0]
    (tmp_path / draft_filename(cell)).write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(DraftFileError) as exc_info:
        FileSkillSynthesizer(tmp_path).synthesize(cell, clusters_for_cell(clusters, cell))
    msg = str(exc_info.value)
    assert str(tmp_path / draft_filename(cell)) in msg
    assert "object" in msg  # states the expected shape


def test_structurally_unusable_payload_raises_never_falls_back_to_template(tmp_path, fixture_layer):
    # Valid JSON, but the default cites only ids not in the cell's clusters — it re-grounds to nothing,
    # parse_synthesizer_output returns None, and the adapter MUST raise (a template fallback would author
    # content the human never drafted).
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    cell = cells[0]
    payload = {
        "name": cell.slug,
        "description": "a draft citing nothing real",
        "default": {"body": "boost everything", "claim_ids": ["clm_0000000000000000"]},
        "sections": [],
    }
    _write_draft(tmp_path, cell, payload)

    with pytest.raises(DraftFileError) as exc_info:
        FileSkillSynthesizer(tmp_path).synthesize(cell, clusters_for_cell(clusters, cell))
    assert str(tmp_path / draft_filename(cell)) in str(exc_info.value)


# ---------------------------------------------------------------------------------------------
# Scoping seam — the missing-file SKIP is implemented by scoping cell selection, never by raising
# ---------------------------------------------------------------------------------------------


def test_scope_clusters_to_cells_is_selection_exact_and_never_mutates(fixture_layer):
    _store, _corpus, _snaps, clusters, cells = fixture_layer
    assert len(cells) >= 2
    dropped = cells[-1]
    available = [c for c in cells if c != dropped]
    genres_before = [list(cl.genre) for cl in clusters]

    scoped = scope_clusters_to_cells(clusters, available)

    # selection over the scoped clusters yields exactly the available cells — the natural skip
    assert set(select_cells(scoped)) == set(available)
    # the originals are untouched (trimmed copies only)
    assert [list(cl.genre) for cl in clusters] == genres_before

    # an available cell's cluster membership is IDENTICAL: same topics, same claims (output-invariance)
    for cell in available:
        scoped_cl = clusters_for_cell(scoped, cell)
        unscoped_cl = clusters_for_cell(clusters, cell)
        assert [cl.topic for cl in scoped_cl] == [cl.topic for cl in unscoped_cl]
        assert [
            ([c.id for c in cl.consensus], [c.id for c in cl.conflicts]) for cl in scoped_cl
        ] == [
            ([c.id for c in cl.consensus], [c.id for c in cl.conflicts]) for cl in unscoped_cl
        ]


def test_cell_scoped_claim_store_keeps_the_gate_claim_index_complete(fixture_layer):
    claim_store, _corpus, _snaps, clusters, cells = fixture_layer
    available = [c for c in cells if c != cells[-1]]

    view = CellScopedClaimStore(claim_store, available)

    # list_claims passes through UNFILTERED — the gate's authoritative claim index stays complete
    assert [c.id for c in view.list_claims()] == [c.id for c in claim_store.list_claims()]
    # list_clusters is the scoped view
    assert set(select_cells(view.list_clusters())) == set(available)
    # everything else delegates to the inner store
    assert view.stats() == claim_store.stats()


# ---------------------------------------------------------------------------------------------
# CLI e2e — `skills synthesize --drafts-dir` over the REAL FilesystemCorpusStore + REAL
# SqliteClaimStore + REAL FilesystemSkillStore (no anthropic SDK, no ANTHROPIC_API_KEY — the point)
# ---------------------------------------------------------------------------------------------

from knowledge_pipeline.adapters import (  # noqa: E402
    FakeClaimExtractor,
    FilesystemCorpusStore,
    KeywordSimilarityIndex,
    SqliteClaimStore,
)
from knowledge_pipeline.claim_fixtures import load_claim_fixtures  # noqa: E402
from knowledge_pipeline.mining_pipeline import MineTarget, MiningPipeline  # noqa: E402
from knowledge_pipeline.pure.snapshot import snapshot_record  # noqa: E402
from knowledge_pipeline.skills_cli import main  # noqa: E402

from .conftest import FIXED_NOW  # noqa: E402


def _real_claim_layer(tmp_path):
    """Mirror ``_fixture_plane`` but with REAL persistence: fs corpus snapshots + sqlite claim layer."""
    corpus_root = tmp_path / "corpus"
    corpus = FilesystemCorpusStore(corpus_root)
    corpus.init_schema()
    claim_corpus = load_claim_fixtures()
    for _vid, transcript in claim_corpus.transcripts.items():
        corpus.write_snapshot(transcript, snapshot_record(transcript, FIXED_NOW))
    claim_store = SqliteClaimStore(corpus_root / "registry.sqlite")
    claim_store.init_schema()
    MiningPipeline(
        FakeClaimExtractor(scripted=claim_corpus.scripted),
        claim_store,
        corpus,
        similarity=KeywordSimilarityIndex(),
    ).mine(
        [MineTarget(video_id=v, genres=claim_corpus.genres.get(v, [])) for v in claim_corpus.video_ids]
    )
    clusters = claim_store.list_clusters()
    cells = select_cells(clusters)
    claim_store.close()
    corpus.close()
    return corpus_root, clusters, cells


def _write_all_drafts(drafts_dir, clusters, cells, *, skip_slug=None, poison_slug=None):
    """One template-derived emit_skill payload per selected cell (optionally skipping/poisoning one)."""
    for cell in cells:
        if cell.slug == skip_slug:
            continue
        payload = _draft_to_payload(template_synthesize(cell, clusters_for_cell(clusters, cell)))
        if cell.slug == poison_slug:
            payload["default"]["body"] += " Boost 999 Hz heavily."
        (drafts_dir / draft_filename(cell)).write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def drafts_plane(tmp_path, monkeypatch):
    """A REAL corpus root + sqlite claim layer + an empty drafts dir + a skills root, no API key set.

    Returns ``(corpus_root, drafts_dir, skills_root, clusters, cells)``.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    corpus_root, clusters, cells = _real_claim_layer(tmp_path)
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    skills_root = tmp_path / "skills-root"
    skills_root.mkdir()
    return corpus_root, drafts_dir, skills_root, clusters, cells


def _synth_argv(drafts_dir, corpus_root, skills_root, *, as_json=False):
    argv = [
        "synthesize", "--drafts-dir", str(drafts_dir),
        "--corpus-root", str(corpus_root), "--skills-root", str(skills_root),
    ]
    return (["--json"] + argv) if as_json else argv


def _run(argv, capsys):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_drafts_dir_e2e_real_stores_no_api_key(drafts_plane, capsys):
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    _write_all_drafts(drafts_dir, clusters, cells)

    rc, out, _err = _run(_synth_argv(drafts_dir, corpus_root, skills_root), capsys)
    assert rc == 0
    assert "authored=5" in out
    assert "rejected=0" in out
    # the real SKILL.md files landed on disk
    assert (skills_root / "skills/production/vocal-layering/rnb/SKILL.md").exists()
    assert (skills_root / "skills/production/drums/amapiano/SKILL.md").exists()

    # persisted in the REAL registry sqlite under the same corpus root
    rc, out, _err = _run(
        ["stats", "--corpus-root", str(corpus_root), "--skills-root", str(skills_root)], capsys
    )
    assert rc == 0
    assert "total_skills:   5" in out
    assert "draft: 5" in out


def test_missing_file_cell_is_skipped_with_a_clear_stderr_line(drafts_plane, capsys):
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    skipped = cells[-1]
    _write_all_drafts(drafts_dir, clusters, cells, skip_slug=skipped.slug)

    rc, out, err = _run(_synth_argv(drafts_dir, corpus_root, skills_root), capsys)
    assert rc == 0
    assert "authored=4" in out
    # the SKIP line names the cell slug AND its expected {stage}__{genre}.json filename
    assert f"SKIP {skipped.slug}" in err
    assert draft_filename(skipped) in err
    # the skipped cell's SKILL.md does NOT exist; the other four do
    assert not (skills_root / skipped.relpath).exists()
    for cell in cells:
        if cell != skipped:
            assert (skills_root / cell.relpath).exists()


def test_skip_does_not_perturb_survivors(drafts_plane, capsys, tmp_path):
    # scoping is output-invariant: the four skills authored in the skip run must be byte-identical
    # (body_sha256) to the same cells in the all-files run.
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    skipped = cells[-1]

    _write_all_drafts(drafts_dir, clusters, cells)
    rc, _out, _err = _run(_synth_argv(drafts_dir, corpus_root, skills_root), capsys)
    assert rc == 0
    rc, out, _err = _run(
        ["--json", "list", "--corpus-root", str(corpus_root), "--skills-root", str(skills_root)], capsys
    )
    all_run = {(s["stage"], s["genre"]): s["body_sha256"] for s in json.loads(out)}

    skip_root = tmp_path / "skills-root-skip"
    skip_root.mkdir()
    skip_drafts = tmp_path / "drafts-skip"
    skip_drafts.mkdir()
    _write_all_drafts(skip_drafts, clusters, cells, skip_slug=skipped.slug)
    rc, _out, _err = _run(_synth_argv(skip_drafts, corpus_root, skip_root), capsys)
    assert rc == 0
    rc, out, _err = _run(
        ["--json", "list", "--corpus-root", str(corpus_root), "--skills-root", str(skip_root)], capsys
    )
    skip_run = {(s["stage"], s["genre"]): s["body_sha256"] for s in json.loads(out)}

    for cell in cells:
        if cell != skipped:
            assert skip_run[(cell.stage, cell.genre)] == all_run[(cell.stage, cell.genre)]


def test_gate_rejects_a_poisoned_file_draft_in_the_report(drafts_plane, capsys):
    # The file plane gets no special pass: a parseable draft asserting an invented parameter value is
    # REJECTED by the unchanged gate and shows in the report with an invented_number reason.
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    poisoned = cells[0]
    _write_all_drafts(drafts_dir, clusters, cells, poison_slug=poisoned.slug)

    rc, out, _err = _run(_synth_argv(drafts_dir, corpus_root, skills_root), capsys)
    assert rc == 0
    assert "authored=4" in out
    assert "rejected=1" in out
    assert "REJECTED" in out
    assert "invented_number" in out
    assert not (skills_root / poisoned.relpath).exists()
    for cell in cells:
        if cell != poisoned:
            assert (skills_root / cell.relpath).exists()


def test_malformed_json_draft_exits_loudly_naming_the_file(drafts_plane, capsys):
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    _write_all_drafts(drafts_dir, clusters, cells)
    bad = drafts_dir / draft_filename(cells[0])
    bad.write_text("{not valid json!!", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(_synth_argv(drafts_dir, corpus_root, skills_root))
    assert str(bad) in str(exc_info.value)


def test_fixtures_and_drafts_dir_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main(["synthesize", "--fixtures", "--drafts-dir", str(tmp_path)])
    assert exc_info.value.code == 2                 # argparse's usage error


def test_nonexistent_drafts_dir_exits_naming_the_directory(tmp_path):
    missing = tmp_path / "no-such-drafts-dir"
    with pytest.raises(SystemExit) as exc_info:
        main([
            "synthesize", "--drafts-dir", str(missing),
            "--corpus-root", str(tmp_path / "corpus"), "--skills-root", str(tmp_path),
        ])
    msg = str(exc_info.value)
    assert str(missing) in msg
    assert ".json" in msg  # says what belongs there


def test_unused_draft_file_warns_on_stderr_and_the_run_authors_normally(drafts_plane, capsys):
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    _write_all_drafts(drafts_dir, clusters, cells)
    (drafts_dir / "bogus__nowhere.json").write_text("{}", encoding="utf-8")

    rc, out, err = _run(_synth_argv(drafts_dir, corpus_root, skills_root), capsys)
    assert rc == 0
    assert "authored=5" in out
    assert "WARNING" in err
    assert "bogus__nowhere.json" in err


def test_json_stdout_stays_parseable_with_a_skip(drafts_plane, capsys):
    # skip/unused lines go to stderr, so `--json` stdout remains a machine-parseable report
    corpus_root, drafts_dir, skills_root, clusters, cells = drafts_plane
    skipped = cells[-1]
    _write_all_drafts(drafts_dir, clusters, cells, skip_slug=skipped.slug)

    rc, out, err = _run(_synth_argv(drafts_dir, corpus_root, skills_root, as_json=True), capsys)
    assert rc == 0
    report = json.loads(out)                        # valid JSON — nothing leaked into stdout
    assert report["authored"] == 4
    assert f"SKIP {skipped.slug}" in err
