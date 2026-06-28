"""FakeReferenceAnalyzer e2e — the full reference-context extraction over fixtures, with fakes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from nameless_workers.adapters.embed_fake import FakeEmbedder
from nameless_workers.adapters.genre_tagger import ClapZeroShotGenreTagger, FakeGenreTagger
from nameless_workers.adapters.reference_analyzer_fake import FakeReferenceAnalyzer
from nameless_workers.adapters.vibe_describer_fake import FakeVibeDescriber
from nameless_workers.domain.reference import FORBIDDEN_MELODIC_FIELDS, ReferenceContext
from nameless_workers.pure.non_melodic import assert_non_melodic, is_non_melodic

# Two distinct "reference tracks" as raw byte blobs — the fake analyzer hashes them; any bytes work.
REF_A = b"finished song A: amapiano, warm, late-night" * 8
REF_B = b"finished song B: deep house, bright, hypnotic" * 8


def test_analyze_produces_a_complete_non_melodic_context():
    analyzer = FakeReferenceAnalyzer()
    rid = uuid4()
    ctx = analyzer.analyze(REF_A, rid)

    assert isinstance(ctx, ReferenceContext)
    assert ctx.reference_track_id == rid
    # Style embedding present (CLAP joint width via the fake).
    assert ctx.style_embedding.dim == 512
    assert len(ctx.style_embedding.vector) == 512
    # Non-melodic targets are sane.
    nm = ctx.non_melodic
    assert nm.tonal_balance.total() == pytest.approx(1.0)
    assert 0.0 <= nm.stereo_width <= 1.0
    assert nm.tempo_bpm_min < nm.tempo_bpm_max
    assert nm.duration_s > 0
    assert ctx.vibe_description  # non-empty prose
    # And the headline guarantee holds on the output.
    assert_non_melodic(ctx)


def test_analyze_is_deterministic_per_input():
    analyzer = FakeReferenceAnalyzer()
    rid = uuid4()
    a = analyzer.analyze(REF_A, rid)
    b = analyzer.analyze(REF_A, rid)
    assert a == b
    # Different audio → different context (the embedding + features change).
    c = analyzer.analyze(REF_B, rid)
    assert c.style_embedding.vector != a.style_embedding.vector


def test_output_serialization_carries_no_melodic_key():
    analyzer = FakeReferenceAnalyzer()
    ctx = analyzer.analyze(REF_A, uuid4())
    # Structural: no melodic field is DECLARED anywhere on the context type.
    assert is_non_melodic(ctx)
    # And no serialized field KEY is a melodic name (check keys, not stringified values — a value
    # like the random UUID hex can innocently contain "f0"; field names cannot).
    payload = ctx.model_dump()
    keys = (
        set(payload)
        | set(payload.get("non_melodic", {}))
        | set(payload.get("style_embedding", {}))
        | set(payload.get("non_melodic", {}).get("tonal_balance", {}))
    )
    assert keys.isdisjoint(FORBIDDEN_MELODIC_FIELDS), keys & FORBIDDEN_MELODIC_FIELDS


def test_summary_is_array_free_and_reports_embedding_dim():
    analyzer = FakeReferenceAnalyzer()
    ctx = analyzer.analyze(REF_A, uuid4())
    summary = ctx.summary()
    assert summary.embedding_dim == 512
    dumped = summary.model_dump()
    assert "style_embedding" not in dumped
    assert "clap_style_embedding" not in dumped


def test_analyzer_composes_injected_real_logic_with_fake_leaves():
    # The fake analyzer is composition-shaped: a real zero-shot tagger (over the fake embedder) +
    # the fake vibe describer slot in unchanged — exercising the real control flow.
    embedder = FakeEmbedder()
    analyzer = FakeReferenceAnalyzer(
        embedder=embedder,
        genre_tagger=ClapZeroShotGenreTagger(embedder, genres=["amapiano", "deep house", "r&b"]),
        vibe_describer=FakeVibeDescriber(),
    )
    ctx = analyzer.analyze(REF_A, uuid4())
    # Genre is one of the candidate labels (or None under a margin) — never a melodic value.
    assert ctx.non_melodic.genre in {"amapiano", "deep house", "r&b", None}


def test_default_fake_genre_tagger_yields_a_known_label():
    analyzer = FakeReferenceAnalyzer(genre_tagger=FakeGenreTagger(genres=["amapiano", "jazz"]))
    ctx = analyzer.analyze(REF_B, uuid4())
    assert ctx.non_melodic.genre in {"amapiano", "jazz"}
