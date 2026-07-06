"""FileClaimExtractor tests — the no-API extraction path over pre-mined ``{video_id}.json`` files.

Three layers, all offline (fakes/tmpdir/sqlite only — no network, no anthropic, no API key):

  * adapter unit tests   — contract parity with ``parse_extractor_output`` (identical normalization to
    the Anthropic adapter's return path), precise error types for missing/malformed files, the reused
    P3 CR-01 path-traversal guard, and the empty-transcript short-circuit.
  * pipeline integration — the UNCHANGED ``MiningPipeline`` judges file-mined claims exactly like API
    output: ``verify_citation`` runs, a missing file becomes a per-video "extract error" skip (the run
    continues), and the present video's cited claims persist.
  * CLI e2e (Task 2)     — ``claims mine --mined-dir`` against the REAL FilesystemCorpusStore + REAL
    SqliteClaimStore with no ANTHROPIC_API_KEY set.
"""

from __future__ import annotations

import json

import pytest

from knowledge_pipeline.adapters import (
    FakeClock,
    InMemoryClaimStore,
    InMemoryCorpusStore,
    KeywordSimilarityIndex,
)
from knowledge_pipeline.adapters.claim_extractor_file import FileClaimExtractor
from knowledge_pipeline.mining_pipeline import MineTarget, MiningPipeline
from knowledge_pipeline.pure.extraction_schema import parse_extractor_output
from knowledge_pipeline.pure.snapshot import snapshot_record

from .conftest import make_transcript

# ---------------------------------------------------------------------------------------------
# Payload helpers — the file body IS the `emit_claims` tool input (EXTRACTION_TOOL_SCHEMA shape).
# ---------------------------------------------------------------------------------------------

LOG_DRUM_LINE = "high pass the log drum around 40 hz"
SIDECHAIN_LINE = "sidechain the bass to the kick around 4 db"


def _claim_entry(
    *,
    quote: str,
    timestamp_ms: int,
    claim_text: str | None = None,
    technique: str = "log-drum",
    stage: str = "drums",
    confidence: float = 0.9,
    **extra: object,
) -> dict:
    entry: dict = {
        "claim_text": claim_text if claim_text is not None else quote,
        "technique": technique,
        "stage": stage,
        "timestamp_ms": timestamp_ms,
        "quote": quote,
        "confidence": confidence,
    }
    entry.update(extra)
    return entry


def _write_mined(mined_dir, video_id: str, claims: list[dict]) -> None:
    (mined_dir / f"{video_id}.json").write_text(
        json.dumps({"claims": claims}), encoding="utf-8"
    )


@pytest.fixture
def mined_dir(tmp_path):
    d = tmp_path / "mined"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------------------------


def test_happy_path_binds_identity_and_reanchors_timestamp(mined_dir):
    transcript = make_transcript(video_id="vid1", segments=[(8.0, 4.0, LOG_DRUM_LINE)])
    payload_claims = [_claim_entry(quote=LOG_DRUM_LINE, timestamp_ms=9000)]  # slightly-off ts
    _write_mined(mined_dir, "vid1", payload_claims)

    extractor = FileClaimExtractor(mined_dir)
    claims = extractor.extract(transcript, genres=["amapiano"])

    assert len(claims) == 1
    c = claims[0]
    assert c.source_video_id == "vid1"                       # bound from the transcript, not the file
    assert c.caption_source is transcript.caption_source     # ditto
    assert c.timestamp_ms == 8000                            # re-anchored to the real segment start
    assert extractor.calls == ["vid1"]

    # Contract parity with the Anthropic adapter's return path: byte-for-byte parse_extractor_output.
    direct = parse_extractor_output(
        {"claims": payload_claims}, transcript, genres=["amapiano"]
    )
    assert [d.id for d in direct] == [c.id]


def test_missing_file_raises_filenotfound_naming_video_and_path(mined_dir):
    transcript = make_transcript(video_id="vid_absent", segments=[(0.0, 5.0, LOG_DRUM_LINE)])
    extractor = FileClaimExtractor(mined_dir)

    with pytest.raises(FileNotFoundError) as exc_info:
        extractor.extract(transcript)
    msg = str(exc_info.value)
    assert "vid_absent" in msg
    assert str(mined_dir / "vid_absent.json") in msg


def test_malformed_json_raises_valueerror_naming_file(mined_dir):
    (mined_dir / "vidbad.json").write_text("{not valid json!!", encoding="utf-8")
    transcript = make_transcript(video_id="vidbad", segments=[(0.0, 5.0, LOG_DRUM_LINE)])

    with pytest.raises(ValueError) as exc_info:
        FileClaimExtractor(mined_dir).extract(transcript)
    assert str(mined_dir / "vidbad.json") in str(exc_info.value)


def test_wrong_top_level_type_raises_valueerror_naming_file(mined_dir):
    # A bare array is valid JSON but NOT the emit_claims tool-input shape.
    (mined_dir / "vidarr.json").write_text(
        json.dumps([_claim_entry(quote=LOG_DRUM_LINE, timestamp_ms=0)]), encoding="utf-8"
    )
    transcript = make_transcript(video_id="vidarr", segments=[(0.0, 5.0, LOG_DRUM_LINE)])

    with pytest.raises(ValueError) as exc_info:
        FileClaimExtractor(mined_dir).extract(transcript)
    assert str(mined_dir / "vidarr.json") in str(exc_info.value)


@pytest.mark.parametrize("evil_id", ["../outside", "..", "a/b", "a\\b", ""])
def test_traversal_video_id_is_rejected_before_touching_the_filesystem(tmp_path, evil_id):
    # Reused P3 CR-01 guard: a crafted video_id must never become an escape-capable path component.
    mined = tmp_path / "mined"
    mined.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"claims": []}), encoding="utf-8")

    transcript = make_transcript(video_id=evil_id, segments=[(0.0, 5.0, LOG_DRUM_LINE)])
    with pytest.raises(ValueError):
        FileClaimExtractor(mined).extract(transcript)
    # nothing outside the mined dir was touched (and the mined dir stays empty)
    assert outside.read_text(encoding="utf-8") == json.dumps({"claims": []})
    assert list(mined.iterdir()) == []


def test_empty_transcript_returns_empty_without_reading_any_file(mined_dir):
    # Poison the file: if the adapter read it, it would raise. Empty segments must short-circuit first
    # (mirrors the Anthropic adapter — nothing to anchor citations against).
    (mined_dir / "vidempty.json").write_text("{poison — not json", encoding="utf-8")
    transcript = make_transcript(video_id="vidempty", segments=[])

    extractor = FileClaimExtractor(mined_dir)
    assert extractor.extract(transcript) == []
    assert extractor.calls == ["vidempty"]


# ---------------------------------------------------------------------------------------------
# Pipeline integration — the UNCHANGED MiningPipeline over the file adapter (fakes only)
# ---------------------------------------------------------------------------------------------


def test_pipeline_judges_file_claims_like_api_claims_and_skips_missing_files(tmp_path):
    corpus = InMemoryCorpusStore()
    clock = FakeClock()
    t1 = make_transcript(video_id="vid1", segments=[(8.0, 4.0, LOG_DRUM_LINE)])
    t2 = make_transcript(video_id="vid2", segments=[(3.0, 4.0, SIDECHAIN_LINE)])
    for t in (t1, t2):
        corpus.write_snapshot(t, snapshot_record(t, clock.now()))

    mined = tmp_path / "mined"
    mined.mkdir()
    _write_mined(mined, "vid1", [_claim_entry(quote=LOG_DRUM_LINE, timestamp_ms=8000)])
    # vid2 has NO mined file — must become a per-video skip, not a crash.

    store = InMemoryClaimStore()
    pipeline = MiningPipeline(
        FileClaimExtractor(mined), store, corpus, similarity=KeywordSimilarityIndex()
    )
    report = pipeline.mine(
        [MineTarget(video_id="vid1", genres=["amapiano"]), MineTarget(video_id="vid2", genres=[])]
    )

    outcomes = {o.video_id: o for o in report.outcomes}
    assert set(outcomes) == {"vid1", "vid2"}
    # missing file => "extract error: ..." detail naming the video; the run completed anyway
    assert outcomes["vid2"].detail.startswith("extract error")
    assert "vid2" in outcomes["vid2"].detail
    assert outcomes["vid2"].kept == 0
    # present file => verify_citation genuinely ran and passed; the claim was kept + persisted
    assert outcomes["vid1"].citations_ok > 0
    assert outcomes["vid1"].kept == 1
    persisted = store.list_claims(source_video_id="vid1")
    assert len(persisted) == 1
    assert persisted[0].quote == LOG_DRUM_LINE
