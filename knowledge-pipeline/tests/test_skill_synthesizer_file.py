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
