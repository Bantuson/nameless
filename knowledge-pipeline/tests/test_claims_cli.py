"""`claims` CLI smoke tests — the offline --fixtures path drives mine + the real sqlite store through argv.

Proves `claims mine | list | show | stats` works end-to-end with no API (FakeClaimExtractor) and the REAL
SqliteClaimStore under a tmp corpus root.
"""

from __future__ import annotations

import json

from knowledge_pipeline.claims_cli import main


def _run(argv, capsys):
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_mine_then_stats(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    rc, out = _run(["mine", "--fixtures", "--corpus-root", root], capsys)
    assert rc == 0
    assert "claims=7" in out
    assert "contested=1" in out

    rc, out = _run(["stats", "--corpus-root", root], capsys)
    assert rc == 0
    assert "total_claims:       7" in out
    assert "contested: 1" in out


def test_list_by_stage_and_conflicts(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    _run(["mine", "--fixtures", "--corpus-root", root], capsys)

    rc, out = _run(["list", "--corpus-root", root, "--by-stage"], capsys)
    assert rc == 0
    assert "## bassline" in out
    assert "## drums" in out

    rc, out = _run(["list", "--corpus-root", root, "--conflicts"], capsys)
    assert rc == 0
    assert "CONFLICT" in out
    assert "log-drum-sound-source" in out
    assert "[flex-synth]" in out
    assert "[layered-samples]" in out


def test_show_traces_a_claim_to_its_source_quote(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    _run(["mine", "--fixtures", "--corpus-root", root], capsys)

    rc, out = _run(["--json", "list", "--corpus-root", root], capsys)
    assert rc == 0
    claims = json.loads(out)
    claim_id = claims[0]["id"]

    rc, out = _run(["show", claim_id, "--corpus-root", root], capsys)
    assert rc == 0
    assert claim_id in out
    assert "quote" in out
    assert "source" in out          # the trace-back: video @ mm:ss


def test_list_by_genre(capsys, tmp_path):
    root = str(tmp_path / "corpus")
    _run(["mine", "--fixtures", "--corpus-root", root], capsys)
    rc, out = _run(["list", "--corpus-root", root, "--by-genre"], capsys)
    assert rc == 0
    assert "## amapiano" in out
    assert "## deep-house" in out
