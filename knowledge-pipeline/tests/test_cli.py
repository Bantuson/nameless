"""CLI smoke tests — the offline ``--fixtures`` path drives the whole pipeline + registry through argv.

Exercises the real FilesystemCorpusStore (sqlite, stdlib) under a tmp corpus root, proving the
``corpus discover | ingest | list | show | stats`` surface works end-to-end with no network.
"""

from __future__ import annotations

from knowledge_pipeline.cli import main


def _run(argv, capsys):
    rc = main(argv)
    out = capsys.readouterr().out
    return rc, out


def test_discover_offline_lists_candidates(capsys, tmp_path):
    rc, out = _run(
        ["discover", "--fixtures", "--corpus-root", str(tmp_path / "c"), "--genres", "amapiano"],
        capsys,
    )
    assert rc == 0
    assert "amapiano_drums_rich" in out
    assert "unique candidate videos" in out


def test_ingest_then_list_and_stats(capsys, tmp_path):
    root = str(tmp_path / "corpus")

    rc, out = _run(["ingest", "--fixtures", "--corpus-root", root], capsys)
    assert rc == 0
    assert "ingested=" in out

    rc, out = _run(["list", "--corpus-root", root, "--by-genre"], capsys)
    assert rc == 0
    assert "## amapiano" in out
    assert "amapiano_drums_rich" in out

    rc, out = _run(["stats", "--corpus-root", root], capsys)
    assert rc == 0
    assert "total:" in out
    assert "by_genre" in out


def test_show_with_segments_prints_timestamps(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    _run(["ingest", "--fixtures", "--corpus-root", root], capsys)

    rc, out = _run(
        ["show", "amapiano_drums_rich", "--corpus-root", root, "--segments", "3"], capsys
    )
    assert rc == 0
    assert "sha256" in out
    assert "keep" in out
    assert "s]" in out  # a "[   6.00s] ..." segment line


def test_list_by_extractability_orders_descending(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    _run(["ingest", "--fixtures", "--corpus-root", root], capsys)
    rc, out = _run(["list", "--corpus-root", root, "--by-extractability"], capsys)
    assert rc == 0
    # the rich tutorial should appear before the sparse vlog in score-descending order
    lines = [ln for ln in out.splitlines() if "_" in ln]
    rich_idx = next(i for i, ln in enumerate(lines) if "amapiano_drums_rich" in ln)
    sparse_idx = next(i for i, ln in enumerate(lines) if "deephouse_atmosphere_sparse" in ln)
    assert rich_idx < sparse_idx
