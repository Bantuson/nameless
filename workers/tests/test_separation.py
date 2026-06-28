"""Pure stem-separation tests — content-hashing, record construction, and the job envelope.

All run against the fake / pure functions (numpy + pydantic only); no demucs, no object store.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from pydantic import TypeAdapter

from nameless_workers.adapters.stem_separator_fake import FakeStemSeparator
from nameless_workers.domain.models import JobEnvelope, SeparateTrackJob
from nameless_workers.domain.separation import HTDEMUCS_6, StemType
from nameless_workers.pure.separation import build_stem_records, content_hash

_ENVELOPE = TypeAdapter(JobEnvelope)


def test_content_hash_is_sha256_hex_and_matches_rust_layout():
    data = b"some stem bytes"
    h = content_hash(data)
    # Lowercase 64-char hex — the SAME content-addressing the Rust object store / FilesystemAudioLoader use.
    assert h == hashlib.sha256(data).hexdigest()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_build_stem_records_names_hashes_and_stamps_provenance():
    rid = uuid4()
    result = FakeStemSeparator().separate(b"track audio")
    records = build_stem_records(rid, result, duration_ms=210_000)

    # One record per stem, in the four-stem order, each carrying the separator provenance.
    assert [r.stem_type for r in records] == [
        StemType.VOCALS,
        StemType.DRUMS,
        StemType.BASS,
        StemType.OTHER,
    ]
    for record, stem in zip(records, result.stems):
        # audio_uri is the content-hash of that stem's bytes.
        assert record.audio_uri == content_hash(stem.audio)
        assert record.reference_track_id == rid
        assert record.separator_model == "fake-demucs"
        assert record.separator_version == "0"
        assert record.duration_ms == 210_000
        assert record.sample_rate == 44_100

    # Distinct stems → distinct content hashes (a real separation never yields identical stems).
    uris = [r.audio_uri for r in records]
    assert len(set(uris)) == len(uris)


def test_six_stem_variant_adds_piano_and_guitar():
    rid = uuid4()
    sep = FakeStemSeparator(stem_types=HTDEMUCS_6, model="fake-demucs_6s")
    records = build_stem_records(rid, sep.separate(b"alt piano track"))
    types = [r.stem_type for r in records]
    assert StemType.PIANO in types
    assert StemType.GUITAR in types
    assert len(records) == 6
    assert all(r.separator_model == "fake-demucs_6s" for r in records)


def test_separate_track_job_round_trips_the_rust_shape():
    rid = uuid4()
    # The exact JSON Rust serializes for JobEnvelope::SeparateTrack.
    raw = json.dumps({"job": "separate_track", "reference_track_id": str(rid)})
    parsed = _ENVELOPE.validate_json(raw)
    assert isinstance(parsed, SeparateTrackJob)
    assert parsed.reference_track_id == rid
    # And the discriminator tag survives a round-trip.
    assert json.loads(parsed.model_dump_json())["job"] == "separate_track"
