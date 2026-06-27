"""audit — citation coverage + flags + a reproducible spot-audit sample (KNOW-11)."""

from __future__ import annotations

import random

from knowledge_pipeline.pure.audit import audit_sample, coverage

from .conftest import FIXED_NOW


def _author(synthesis_plane):
    pipeline, skill_store, _claim_store, _corpus = synthesis_plane
    pipeline.synthesize()
    return skill_store


def test_coverage_flags_a_contested_default(synthesis_plane):
    store = _author(synthesis_plane)
    amapiano_drums = next(s for s in store.list_skills() if s.slug == "amapiano-drums")
    cov = coverage(amapiano_drums)
    assert "contested-default" in cov.flags
    assert cov.confidence_tier == "LOW"


def test_coverage_flags_a_single_source_default(synthesis_plane):
    store = _author(synthesis_plane)
    vocal = next(s for s in store.list_skills() if s.slug == "rnb-vocal-layering")
    cov = coverage(vocal)
    assert "single-source-default" in cov.flags


def test_high_corroboration_skill_is_clean_and_high(synthesis_plane):
    store = _author(synthesis_plane)
    dh = next(s for s in store.list_skills() if s.slug == "deep-house-bassline")
    cov = coverage(dh)
    assert cov.confidence_tier == "HIGH"
    assert "single-source-default" not in cov.flags
    assert "contested-default" not in cov.flags


def test_audit_sample_is_reproducible_under_a_seed(synthesis_plane):
    store = _author(synthesis_plane)
    skills = store.list_skills()
    a = audit_sample(skills, sample_size=2, rng=random.Random(7))
    b = audit_sample(skills, sample_size=2, rng=random.Random(7))
    assert [c.skill_id for c in a.sampled] == [c.skill_id for c in b.sampled]
    assert a.sample_size == 2


def test_audit_only_samples_drafts_by_default(synthesis_plane):
    store = _author(synthesis_plane)
    report = audit_sample(store.list_skills(), sample_size=10, rng=random.Random(0))
    assert all(c.status == "draft" for c in report.sampled)
    assert report.draft == report.total_skills  # nothing promoted yet
    assert report.promoted == 0


def test_audit_counts_flagged_in_the_sample(synthesis_plane):
    store = _author(synthesis_plane)
    report = audit_sample(store.list_skills(), sample_size=10, rng=random.Random(0))
    # the contested + single-source skills are flagged; the 3-source bassline cells are clean
    assert 0 < report.flagged < report.sample_size
