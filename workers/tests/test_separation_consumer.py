"""SeparationJobConsumer tests — the full orchestration over fakes (retention, provenance, idempotency).

Exercises the real control flow (load → separate → content-hash → retain → persist) with deterministic
fakes; no demucs, no object store, no Postgres.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from nameless_workers.adapters.stem_separator_fake import FakeStemSeparator
from nameless_workers.adapters.stem_store_mem import (
    InMemoryStemBlobStore,
    InMemoryStemRecordStore,
)
from nameless_workers.adapters.track_loader_fake import InMemoryTrackLoader
from nameless_workers.domain.models import SeparateTrackJob
from nameless_workers.domain.separation import HTDEMUCS_6, StemType
from nameless_workers.pure.separation import content_hash
from nameless_workers.separation_consumer import (
    SeparationJobConsumer,
    TrackNotFound,
)

TRACK_BYTES = b"a finished amapiano track, retained for sampling" * 16


def _consumer(separator=None):
    rid = uuid4()
    loader = InMemoryTrackLoader({rid: TRACK_BYTES})
    blobs = InMemoryStemBlobStore()
    records = InMemoryStemRecordStore()
    consumer = SeparationJobConsumer(
        track_loader=loader,
        separator=separator or FakeStemSeparator(),
        blob_store=blobs,
        record_store=records,
    )
    return rid, consumer, blobs, records


def test_separation_retains_named_stems_with_model_version_provenance():
    rid, consumer, blobs, records = _consumer()
    outcome = consumer.handle(SeparateTrackJob(reference_track_id=rid))

    # Four named stems retained + recorded.
    assert outcome.n_stems == 4
    assert outcome.stem_types == ["vocals", "drums", "bass", "other"]
    assert not outcome.skipped

    stored = records.list_stems(rid)
    assert len(stored) == 4
    # Provenance (model + version) is on every retained record.
    assert all(r.separator_model == "fake-demucs" for r in stored)
    assert all(r.separator_version == "0" for r in stored)
    # Every stem's bytes are retained in the blob store under its content-hash key.
    for r in stored:
        assert r.audio_uri in blobs
        assert content_hash(blobs.get(r.audio_uri)) == r.audio_uri


def test_separation_is_idempotent_under_redelivery():
    rid, consumer, blobs, records = _consumer()
    job = SeparateTrackJob(reference_track_id=rid)

    first = consumer.handle(job)
    assert first.skipped is False
    assert len(records.list_stems(rid)) == 4
    blob_count_after_first = len(blobs.blobs)

    # Re-deliver the SAME job: deterministic separation → same hashes → nothing new retained.
    second = consumer.handle(job)
    assert second.skipped is True
    assert second.stem_uris == first.stem_uris
    assert len(records.list_stems(rid)) == 4  # no duplicate rows
    assert len(blobs.blobs) == blob_count_after_first  # no new blobs


def test_six_stem_model_retains_piano_and_guitar():
    rid, consumer, _blobs, records = _consumer(
        separator=FakeStemSeparator(stem_types=HTDEMUCS_6, model="fake-demucs_6s")
    )
    outcome = consumer.handle(SeparateTrackJob(reference_track_id=rid))
    assert outcome.n_stems == 6
    types = {r.stem_type for r in records.list_stems(rid)}
    assert StemType.PIANO in types
    assert StemType.GUITAR in types
    assert all(r.separator_model == "fake-demucs_6s" for r in records.list_stems(rid))


def test_unknown_track_raises_track_not_found():
    _rid, consumer, _blobs, _records = _consumer()
    with pytest.raises(TrackNotFound):
        consumer.handle(SeparateTrackJob(reference_track_id=uuid4()))  # not in the loader


def test_outcome_is_compact_and_carries_no_audio():
    rid, consumer, _blobs, _records = _consumer()
    outcome = consumer.handle(SeparateTrackJob(reference_track_id=rid))
    # The outcome (safe to log) carries only ids/labels/hashes — never stem bytes.
    dumped = outcome.model_dump_json()
    assert "vocals" in dumped
    # No raw stem bytes leak into the compact outcome.
    assert "\\u0000" not in dumped
    assert isinstance(outcome.stem_uris[0], str) and len(outcome.stem_uris[0]) == 64
