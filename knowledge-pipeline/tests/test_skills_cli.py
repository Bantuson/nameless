"""`skills` CLI smoke tests — the offline --fixtures path drives synthesize + the real fs store through argv.

Proves `skills synthesize | list | show | audit | promote | stats` works end-to-end with no API
(FakeSkillSynthesizer) and the REAL FilesystemSkillStore under a tmp root.
"""

from __future__ import annotations

import json
from pathlib import Path

from knowledge_pipeline.skills_cli import main


def _run(argv, capsys):
    rc = main(argv)
    return rc, capsys.readouterr().out


def _synthesize(tmp_path, capsys):
    root = str(tmp_path)
    corpus = str(tmp_path / "corpus")
    rc, out = _run(["synthesize", "--fixtures", "--corpus-root", corpus, "--skills-root", root], capsys)
    return rc, out, root, corpus


def test_synthesize_authors_the_p1_cells_and_writes_files(capsys, tmp_path):
    rc, out, root, _corpus = _synthesize(tmp_path, capsys)
    assert rc == 0
    assert "authored=5" in out
    assert "rejected=0" in out
    # the real SKILL.md files landed on disk
    assert (Path(root) / "skills/production/drums/amapiano/SKILL.md").exists()
    assert (Path(root) / "skills/production/vocal-layering/rnb/SKILL.md").exists()


def test_list_by_genre(capsys, tmp_path):
    _synthesize(tmp_path, capsys)
    rc, out = _run(["list", "--corpus-root", str(tmp_path / "corpus"), "--skills-root", str(tmp_path),
                    "--by-genre"], capsys)
    assert rc == 0
    assert "## amapiano" in out
    assert "## deep-house" in out


def test_show_traces_to_citations_and_body(capsys, tmp_path):
    _synthesize(tmp_path, capsys)
    rc, out = _run(["--json", "list", "--corpus-root", str(tmp_path / "corpus"),
                    "--skills-root", str(tmp_path)], capsys)
    skill_id = json.loads(out)[0]["id"]

    rc, out = _run(["show", skill_id, "--corpus-root", str(tmp_path / "corpus"),
                    "--skills-root", str(tmp_path), "--body"], capsys)
    assert rc == 0
    assert skill_id in out
    assert "## Default — act on this" in out  # the body was printed
    assert "confidence" in out


def test_audit_surfaces_a_seeded_sample_with_flags(capsys, tmp_path):
    _synthesize(tmp_path, capsys)
    rc, out = _run(["audit", "--corpus-root", str(tmp_path / "corpus"), "--skills-root", str(tmp_path),
                    "--sample", "5", "--seed", "0"], capsys)
    assert rc == 0
    assert "human spot-audit sample" in out
    assert "contested-default" in out or "single-source-default" in out


def test_promote_is_human_gated(capsys, tmp_path):
    _synthesize(tmp_path, capsys)
    corpus, root = str(tmp_path / "corpus"), str(tmp_path)
    rc, out = _run(["--json", "list", "--corpus-root", corpus, "--skills-root", root], capsys)
    skill_id = next(
        s["id"] for s in json.loads(out) if s["genre"] == "deep-house" and s["stage"] == "bassline"
    )

    # without --yes: NOT promoted (the human gate)
    rc, out = _run(["promote", skill_id, "--corpus-root", corpus, "--skills-root", root], capsys)
    assert rc == 0
    assert "NOT promoted" in out
    rc, out = _run(["show", skill_id, "--corpus-root", corpus, "--skills-root", root], capsys)
    assert "status       draft" in out

    # with --yes: promoted
    rc, out = _run(["promote", skill_id, "--corpus-root", corpus, "--skills-root", root, "--yes"], capsys)
    assert rc == 0
    assert "PROMOTED" in out
    rc, out = _run(["show", skill_id, "--corpus-root", corpus, "--skills-root", root], capsys)
    assert "status       promoted" in out


def test_stats(capsys, tmp_path):
    _synthesize(tmp_path, capsys)
    rc, out = _run(["stats", "--corpus-root", str(tmp_path / "corpus"), "--skills-root", str(tmp_path)], capsys)
    assert rc == 0
    assert "total_skills:   5" in out
    assert "HIGH" in out
