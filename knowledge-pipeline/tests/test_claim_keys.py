"""Pure key/normalization helpers (domain.keys) — the deterministic substrate everything keys on."""

from __future__ import annotations

from knowledge_pipeline.domain.keys import (
    compute_claim_id,
    normalize_key,
    normalize_text,
    tokens,
    topic_key,
)


def test_normalize_text_folds_case_and_punctuation_keeps_numbers_and_units():
    assert normalize_text("Cut around 300 Hz!") == "cut around 300 hz"
    assert normalize_text("  -6 dB,  fast  attack ") == "6 db fast attack"  # punct -> space, ws collapsed


def test_normalize_key_is_kebab():
    assert normalize_key("Log Drum") == "log-drum"
    assert normalize_key("FL Studio FLEX") == "fl-studio-flex"
    assert normalize_key(None) == ""
    assert normalize_key("  ") == ""


def test_topic_key_combines_normalized_stage_and_technique():
    assert topic_key("Vocal Layering", "Vocal Stacking") == "vocal-layering/vocal-stacking"


def test_tokens_preserve_hyphenated_terms():
    assert "high-pass" in tokens("High-pass the sub-bass")
    assert "sub-bass" in tokens("High-pass the sub-bass")


def test_compute_claim_id_stable_and_normalization_insensitive():
    a = compute_claim_id("v", 8000, "High-pass the sub around 30 Hz.")
    b = compute_claim_id("v", 8000, "high-pass   the sub around 30 hz")
    assert a == b
    assert compute_claim_id("v", 8001, "x") != compute_claim_id("v", 8000, "x")
