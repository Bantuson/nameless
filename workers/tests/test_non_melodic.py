"""The restricted-feature / non-cloning invariant — structural seal + runtime tripwire (REF-03)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from nameless_workers.domain.reference import (
    NonMelodicFeatures,
    ReferenceContext,
    TonalBalance,
)
from nameless_workers.domain.models import Embedding
from nameless_workers.pure.non_melodic import (
    MelodicLeakError,
    assert_non_melodic,
    is_non_melodic,
)


def _tonal() -> TonalBalance:
    return TonalBalance(low=0.3, low_mid=0.25, mid=0.2, high_mid=0.15, high=0.1)


def _features() -> NonMelodicFeatures:
    return NonMelodicFeatures(
        tonal_balance=_tonal(),
        stereo_width=0.4,
        lufs=-9.0,
        tempo_bpm_min=110.0,
        tempo_bpm_max=116.0,
        genre="amapiano",
        sample_rate=44_100,
        duration_s=180.0,
    )


def _context() -> ReferenceContext:
    return ReferenceContext(
        reference_track_id="00000000-0000-0000-0000-000000000001",
        style_embedding=Embedding(model_name="fake", dim=4, vector=[0.5, 0.5, 0.5, 0.5]),
        non_melodic=_features(),
        vibe_description="warm, late-night, spacious",
        analyzer_version="t",
    )


# ---- structural seal: the type cannot be CONSTRUCTED with a melodic field ----


def test_non_melodic_features_rejects_a_melodic_field():
    # extra="forbid" → passing an f0/chroma/key kwarg raises, by construction.
    for bad in ("f0", "chroma", "chroma_mean", "melody", "key", "chords", "structure"):
        with pytest.raises(ValidationError):
            NonMelodicFeatures(
                tonal_balance=_tonal(),
                stereo_width=0.4,
                lufs=-9.0,
                tempo_bpm_min=110.0,
                tempo_bpm_max=116.0,
                **{bad: [1.0, 2.0, 3.0]},
            )


def test_reference_context_rejects_a_melodic_field():
    with pytest.raises(ValidationError):
        ReferenceContext(
            reference_track_id="00000000-0000-0000-0000-000000000001",
            style_embedding=Embedding(model_name="fake", dim=2, vector=[1.0, 0.0]),
            non_melodic=_features(),
            vibe_description="x",
            analyzer_version="t",
            chroma=[[0.0] * 12],  # not a field → forbidden
        )


# ---- runtime tripwire: assert_non_melodic passes for the sealed types ----


def test_assert_non_melodic_passes_for_the_real_types():
    assert is_non_melodic(_features())
    assert is_non_melodic(_context())
    # Does not raise.
    assert_non_melodic(_features())
    assert_non_melodic(_context())


def test_assert_non_melodic_fires_on_a_model_that_declares_a_melodic_field():
    # A deliberately-bad model to prove the tripwire catches a future regression.
    class LeakyContext(BaseModel):
        model_config = ConfigDict(extra="forbid")

        reference_track_id: str
        chroma_mean: list[float] = []  # the kind of column that must never exist

    leaky = LeakyContext(reference_track_id="x", chroma_mean=[0.0] * 12)
    assert not is_non_melodic(leaky)
    with pytest.raises(MelodicLeakError):
        assert_non_melodic(leaky)


def test_tripwire_recurses_into_nested_models():
    # A model whose nested type carries a melodic field is also caught.
    class BadInner(BaseModel):
        f0: list[float] = []

    class Outer(BaseModel):
        inner: BadInner = BadInner()

    with pytest.raises(MelodicLeakError):
        assert_non_melodic(Outer())
