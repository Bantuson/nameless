"""Reference job-envelope + model round-trips — the cross-language JSON contract with Rust."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from nameless_workers.domain.models import AnalyzeReferenceJob, JobEnvelope
from nameless_workers.domain.reference import (
    NonMelodicFeatures,
    ReferenceContext,
    ReferenceContextSummary,
    TonalBalance,
)
from nameless_workers.domain.models import Embedding

_ENVELOPE = TypeAdapter(JobEnvelope)


def test_analyze_reference_job_matches_the_rust_json_shape():
    rid = uuid4()
    job = AnalyzeReferenceJob(reference_track_id=rid)
    payload = json.loads(job.model_dump_json())
    # Exactly the shape nameless_core::job::JobEnvelope serializes (internally tagged on `job`).
    assert payload == {"job": "analyze_reference", "reference_track_id": str(rid)}


def test_envelope_union_discriminates_analyze_reference():
    rid = uuid4()
    parsed = _ENVELOPE.validate_python(
        {"job": "analyze_reference", "reference_track_id": str(rid)}
    )
    assert isinstance(parsed, AnalyzeReferenceJob)
    assert parsed.reference_track_id == rid


def test_envelope_union_still_parses_the_phase2_jobs():
    fid = str(uuid4())
    fe = _ENVELOPE.validate_python({"job": "feature_extract", "fragment_id": fid})
    sep = _ENVELOPE.validate_python({"job": "separate", "fragment_id": fid})
    assert fe.job == "feature_extract"
    assert sep.job == "separate"


def test_unknown_job_tag_is_rejected():
    with pytest.raises(ValidationError):
        _ENVELOPE.validate_python({"job": "teleport", "fragment_id": str(uuid4())})


def test_reference_context_summary_round_trips_without_a_vector():
    summary = ReferenceContextSummary(
        reference_track_id=uuid4(),
        genre="amapiano",
        tempo_bpm_min=110.0,
        tempo_bpm_max=116.0,
        lufs=-9.5,
        tonal_balance=TonalBalance(low=0.3, low_mid=0.25, mid=0.2, high_mid=0.15, high=0.1),
        stereo_width=0.4,
        vibe_description="warm",
        embedding_dim=512,
        analyzer_version="v",
    )
    back = ReferenceContextSummary.model_validate_json(summary.model_dump_json())
    assert back == summary
    payload = json.loads(summary.model_dump_json())
    # The summary reports the embedding's DIMENSION only — no vector field of any name.
    assert payload["embedding_dim"] == 512
    assert "style_embedding" not in payload
    assert "clap_style_embedding" not in payload


def test_context_summary_projection_drops_the_vector():
    ctx = ReferenceContext(
        reference_track_id=uuid4(),
        style_embedding=Embedding(model_name="fake", dim=512, vector=[0.01] * 512),
        non_melodic=NonMelodicFeatures(
            tonal_balance=TonalBalance(low=0.3, low_mid=0.25, mid=0.2, high_mid=0.15, high=0.1),
            stereo_width=0.4,
            lufs=-9.0,
            tempo_bpm_min=110.0,
            tempo_bpm_max=116.0,
            genre="amapiano",
            sample_rate=44_100,
            duration_s=180.0,
        ),
        vibe_description="warm",
        analyzer_version="v",
    )
    s = ctx.summary()
    assert s.embedding_dim == 512
    assert s.genre == "amapiano"
    # The summary carries the dim, not the 512-length vector (use pydantic's JSON serializer, which
    # handles UUID etc.; the raw embedding value 0.01 must not appear anywhere).
    assert "0.01" not in s.model_dump_json()
