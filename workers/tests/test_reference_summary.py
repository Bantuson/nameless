"""Compact reference-summary formatting — array-free by construction."""

from __future__ import annotations

from uuid import uuid4

from nameless_workers.domain.models import Embedding
from nameless_workers.domain.reference import (
    NonMelodicFeatures,
    ReferenceContext,
    TonalBalance,
)
from nameless_workers.pure.reference_summary import (
    format_summary_line,
    summary_to_compact_dict,
)


def _context() -> ReferenceContext:
    return ReferenceContext(
        reference_track_id=uuid4(),
        style_embedding=Embedding(model_name="fake-clap-0", dim=512, vector=[0.04] * 512),
        non_melodic=NonMelodicFeatures(
            tonal_balance=TonalBalance(low=0.3, low_mid=0.25, mid=0.2, high_mid=0.15, high=0.1),
            stereo_width=0.42,
            lufs=-9.5,
            tempo_bpm_min=110.0,
            tempo_bpm_max=116.0,
            genre="amapiano",
            sample_rate=44_100,
            duration_s=200.0,
        ),
        vibe_description="warm, spacious, late-night",
        analyzer_version="fake-ref-0",
    )


def test_compact_dict_has_embedding_dim_not_the_vector():
    d = summary_to_compact_dict(_context().summary())
    assert d["embedding_dim"] == 512
    # The big vector value (0.04) must not appear anywhere in the compact dict.
    assert "0.04" not in str(d)
    # The 5 tonal-balance ratios are fine (compact scalars), but no 512-length list is present.
    assert len(d["tonal_balance"]) == 5
    assert d["genre"] == "amapiano"


def test_format_line_is_one_compact_line_without_the_vector():
    line = format_summary_line(_context().summary())
    assert "\n" not in line
    assert "amapiano" in line
    assert "warm, spacious, late-night" in line
    assert "0.04" not in line  # the embedding never leaks into the line


def test_summary_serialization_excludes_the_embedding_field():
    summary = _context().summary()
    payload = summary.model_dump()
    assert "style_embedding" not in payload
    assert "clap_style_embedding" not in payload
    assert payload["embedding_dim"] == 512
