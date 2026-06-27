"""Typed-boundary tests — the job envelope must match the Rust JSON shape byte-for-byte."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from nameless_workers.domain.models import (
    FeatureExtractJob,
    JobEnvelope,
    SearchHit,
    SeparateJob,
)

_envelope_adapter = TypeAdapter(JobEnvelope)


def test_feature_extract_job_serializes_to_rust_shape():
    fid = uuid4()
    job = FeatureExtractJob(fragment_id=fid)
    dumped = job.model_dump()
    # Internally tagged on `job`, snake_case — matches `#[serde(tag="job", rename_all="snake_case")]`.
    assert dumped["job"] == "feature_extract"
    assert dumped["fragment_id"] == fid


def test_rust_shaped_json_parses_through_the_discriminated_union():
    fid = uuid4()
    # Exactly what Rust serde emits for JobEnvelope::FeatureExtract.
    payload = {"job": "feature_extract", "fragment_id": str(fid)}
    env = _envelope_adapter.validate_python(payload)
    assert isinstance(env, FeatureExtractJob)
    assert env.fragment_id == fid


def test_separate_variant_parses():
    fid = uuid4()
    env = _envelope_adapter.validate_python({"job": "separate", "fragment_id": str(fid)})
    assert isinstance(env, SeparateJob)
    assert env.fragment_id == fid


def test_unknown_job_tag_is_rejected():
    with pytest.raises(ValidationError):
        _envelope_adapter.validate_python({"job": "transcode", "fragment_id": str(uuid4())})


def test_search_hit_has_no_vector_field():
    # The compact-output contract is enforced at the type level: SearchHit cannot carry a vector.
    fields = set(SearchHit.model_fields.keys())
    assert fields == {"fragment_id", "key", "tempo_bpm", "score"}
    for forbidden in ("vector", "embedding", "chroma", "f0", "audio"):
        assert forbidden not in fields
