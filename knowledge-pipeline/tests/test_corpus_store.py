"""CorpusStore contract tests — run against BOTH the in-memory fake AND the real sqlite+filesystem store.

The real FilesystemCorpusStore needs no extra install (sqlite3/json are stdlib), so the SAME contract
runs against the actual persistence path on the base env — honest verification, not just a fake. The
``store`` fixture is parameterized over both implementations so every assertion holds for each.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from knowledge_pipeline.adapters import FilesystemCorpusStore, InMemoryCorpusStore
from knowledge_pipeline.domain.models import (
    CorpusEntry,
    Verdict,
)
from knowledge_pipeline.pure.extractability import extractability_score
from knowledge_pipeline.pure.snapshot import snapshot_record

from .conftest import make_transcript

NOW = _dt.datetime(2026, 6, 27, 10, 0, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture(params=["memory", "filesystem"])
def store(request, tmp_path):
    if request.param == "memory":
        s = InMemoryCorpusStore()
    else:
        s = FilesystemCorpusStore(tmp_path / "corpus")
    s.init_schema()
    yield s
    if hasattr(s, "close"):
        s.close()


def _entry(video, *, genre="amapiano", stage="drums", caption="manual", segs=None) -> CorpusEntry:
    from knowledge_pipeline.domain.models import CaptionSource, VideoRef

    segs = segs or [(0.0, 6.0, "high pass the log drum around 40 hz and sidechain the bass to the kick")]
    t = make_transcript(video_id=video, caption_source=CaptionSource(caption), segments=segs)
    rec = snapshot_record(t, NOW)
    extr = extractability_score(t)
    vid = VideoRef(video_id=video, title=f"title {video}", genre=genre, stage=stage, query_origin="q")
    return CorpusEntry(video=vid, snapshot=rec, extractability=extr, ingested_at=NOW), t


def test_register_and_get_roundtrip(store):
    entry, transcript = _entry("a")
    store.write_snapshot(transcript, entry.snapshot)
    store.register(entry)

    got = store.get("a")
    assert got is not None
    assert got.video.video_id == "a"
    assert got.snapshot.content_sha256 == entry.snapshot.content_sha256
    assert got.extractability.score == entry.extractability.score
    assert got.video.genre == "amapiano"


def test_idempotency_has_and_known_ids(store):
    entry, transcript = _entry("a")
    assert store.has("a") is False
    store.write_snapshot(transcript, entry.snapshot)
    store.register(entry)
    assert store.has("a") is True
    assert store.known_ids() == {"a"}


def test_snapshot_roundtrip_preserves_timestamped_segments(store):
    segs = [(8.0, 4.0, "high pass the log drum"), (13.0, 5.0, "sidechain the bass to the kick around 40 hz")]
    entry, transcript = _entry("a", segs=segs)
    store.write_snapshot(transcript, entry.snapshot)
    store.register(entry)

    loaded = store.load_snapshot("a")
    assert loaded is not None
    assert [round(s.start_s, 2) for s in loaded.segments] == [8.0, 13.0]
    assert loaded.segments[0].text == "high pass the log drum"
    # the durable evidence supports Phase-4 `video_id @ ts` citation
    assert loaded.video_id == "a"


def test_register_is_upsert(store):
    entry, transcript = _entry("a")
    store.write_snapshot(transcript, entry.snapshot)
    store.register(entry)
    store.register(entry)  # second time must not duplicate
    assert len(store.list_entries()) == 1


def test_list_filters_by_genre_and_verdict(store):
    e1, t1 = _entry("a", genre="amapiano")
    e2, t2 = _entry("b", genre="deep-house")
    for e, t in ((e1, t1), (e2, t2)):
        store.write_snapshot(t, e.snapshot)
        store.register(e)

    ama = store.list_entries(genre="amapiano")
    assert {e.video.video_id for e in ama} == {"a"}

    keeps = store.list_entries(verdict=Verdict.KEEP)
    assert all(e.extractability.verdict is Verdict.KEEP for e in keeps)


def test_list_orders_by_extractability(store):
    # a rich one (high score) and a sparse one (low score)
    rich, t_rich = _entry("rich")
    sparse, t_sparse = _entry(
        "sparse",
        segs=[(0.0, 8.0, "yeah man this vibe is so clean i love it"), (60.0, 8.0, "shout out everyone")],
        caption="manual",
    )
    for e, t in ((rich, t_rich), (sparse, t_sparse)):
        store.write_snapshot(t, e.snapshot)
        store.register(e)

    ordered = store.list_entries(order_by_score=True)
    scores = [e.extractability.score for e in ordered]
    assert scores == sorted(scores, reverse=True)
    assert ordered[0].video.video_id == "rich"


def test_stats_rollup(store):
    e1, t1 = _entry("a", genre="amapiano")
    e2, t2 = _entry("b", genre="amapiano")
    e3, t3 = _entry("c", genre="deep-house")
    for e, t in ((e1, t1), (e2, t2), (e3, t3)):
        store.write_snapshot(t, e.snapshot)
        store.register(e)

    stats = store.stats()
    assert stats.total == 3
    assert stats.by_genre["amapiano"] == 2
    assert stats.by_genre["deep-house"] == 1
    assert sum(stats.by_verdict.values()) == 3


def test_get_missing_returns_none(store):
    assert store.get("nope") is None
    assert store.load_snapshot("nope") is None


def test_malicious_video_id_is_rejected_before_touching_the_filesystem(tmp_path):
    # CR-01: a crafted id must never escape the corpus root on write OR read. `pathlib`'s `/` does not
    # collapse `..`, so without the guard `../../../etc/passwd` would be an arbitrary-file primitive.
    root = tmp_path / "corpus"
    store = FilesystemCorpusStore(root)
    store.init_schema()
    entry, transcript = _entry("a")
    evil = entry.snapshot.model_copy(update={"video_id": "../../../../etc/cron.d/x"})
    evil_transcript = transcript.model_copy(update={"video_id": "../../../../etc/cron.d/x"})

    with pytest.raises(ValueError):
        store.write_snapshot(evil_transcript, evil)
    with pytest.raises(ValueError):
        store.load_snapshot("../../../../etc/passwd")
    # the snapshots dir contains nothing outside itself (no escape happened)
    assert list((root / "snapshots").glob("*.json")) == []
    store.close()


def test_load_snapshot_detects_tampered_evidence_file(tmp_path):
    # WR-02: the integrity guarantee the docstrings advertise is now real — a hand-edited snapshot file
    # whose content no longer matches the stored sha256 is rejected on read.
    import json

    root = tmp_path / "corpus"
    store = FilesystemCorpusStore(root)
    store.init_schema()
    entry, transcript = _entry("a")
    store.write_snapshot(transcript, entry.snapshot)
    store.register(entry)
    assert store.load_snapshot("a") is not None  # untouched file re-verifies cleanly

    snap_file = root / "snapshots" / "a.json"
    payload = json.loads(snap_file.read_text(encoding="utf-8"))
    payload["segments"][0]["text"] = "tampered: cut at 9000 hz"  # content drift, sha256 left stale
    snap_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError):
        store.load_snapshot("a")
    store.close()


def test_filesystem_store_persists_across_instances(tmp_path):
    # Reopen the same corpus dir with a fresh store ⇒ the registry + snapshot survive (durability).
    root = tmp_path / "corpus"
    s1 = FilesystemCorpusStore(root)
    s1.init_schema()
    entry, transcript = _entry("a")
    s1.write_snapshot(transcript, entry.snapshot)
    s1.register(entry)
    s1.close()

    s2 = FilesystemCorpusStore(root)
    s2.init_schema()
    assert s2.has("a")
    loaded = s2.load_snapshot("a")
    assert loaded is not None and loaded.video_id == "a"
    s2.close()
