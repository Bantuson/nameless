"""Pure key/normalization helpers — the deterministic substrate the claim layer keys on.

These are PURE functions (stdlib only, no I/O, no global state): lowercase/collapse normalization,
the ``(stage, technique)`` topic key, and the content-addressed claim id. They live in ``domain``
(not ``pure``) because the domain models themselves depend on them (``Claim.id`` is a content hash of
its own fields) — and a domain type must stay free of adapters/I/O, which these are.

Why a *content-addressed* claim id (sha1 of ``video_id | timestamp_ms | normalized_text``):
  * **Idempotent re-mining.** Re-running extraction over the same source yields the *same* id, so the
    store upserts in place instead of duplicating (PITFALLS #2: incremental, idempotent).
  * **Dedup for free.** Two extractions of the same sentence collapse to one row.
  * **No invented identity.** The LLM never assigns ids (it would hallucinate them); the id is computed
    from the citation anchor + the claim text, so it can never drift from its evidence.

Why normalization keeps digits + unit letters: a claim's value ("300 hz", "-6 db") is load-bearing
craft — the topic/citation matching must NOT strip "300" or "hz". We only fold case, punctuation, and
whitespace.
"""

from __future__ import annotations

import hashlib
import re

# Keep alphanumerics (incl. the digits/units that carry the craft) and spaces; fold everything else.
_NON_KEY = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9][a-z0-9'\-]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace. Pure.

    Used for citation matching and dedup — ``"Cut around 300 Hz!"`` and ``"cut around 300 hz"`` compare
    equal, but ``"300"`` and ``"hz"`` survive (numbers/units are craft, never discarded).
    """
    lowered = text.lower()
    spaced = _NON_KEY.sub(" ", lowered)
    return _WS.sub(" ", spaced).strip()


def tokens(text: str) -> list[str]:
    """Lowercased word tokens (hyphenated craft terms like ``high-pass`` preserved). Pure."""
    return _WORD.findall(text.lower())


def _norm_number(token: str) -> str:
    """Canonicalize a numeric token so ``030`` == ``30`` and ``30.0`` == ``30``. Pure."""
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token.lstrip("0") or "0"


def numbers(text: str) -> set[str]:
    """Every numeric token (int/decimal) in ``text``, canonicalized. Pure.

    The kernel of Phase 5's invented-number gate (KNOW-08): a producer parameter — ``300`` (Hz),
    ``-6`` (dB), ``120`` (BPM), ``808`` — is load-bearing craft. The gate extracts the numbers a skill
    *asserts* and demands every one of them also appear in a CITED source quote; a confident-sounding
    value present nowhere in the evidence ("high-pass at 40 Hz" when no source said 40) is the single
    worst GIGO failure, and surfacing it as a set difference makes the reject mechanical, not a judgment
    call. We compare the magnitude only (``30`` from "30 Hz") because the unit travels in the prose, not
    the number — so "30 hz" in a quote grounds "30 Hz" in the skill, but a wrong magnitude never passes.
    """
    return {_norm_number(n) for n in _NUMBER.findall(text)}


def normalize_key(value: str | None) -> str:
    """Canonical kebab key for a stage/technique/stance label (``"Log Drum"`` -> ``"log-drum"``). Pure."""
    if not value:
        return ""
    lowered = value.strip().lower()
    return _NON_KEY.sub("-", lowered).strip("-")


def topic_key(stage: str, technique: str) -> str:
    """The cross-reference grouping key: ``"<stage>/<technique>"``, both normalized. Pure.

    Deliberately genre-AGNOSTIC: a universal technique (e.g. high-passing the sub) should corroborate
    *across* genres rather than fragmenting per genre. Genre conflation is guarded at the *claim* level
    (each claim carries its own evidenced ``genre[]``), not by splitting the topic key. See LEARNING §4.
    """
    return f"{normalize_key(stage)}/{normalize_key(technique)}"


def compute_claim_id(source_video_id: str, timestamp_ms: int, claim_text: str) -> str:
    """Deterministic, content-addressed claim id. Pure.

    sha1 over ``video_id | timestamp_ms | normalize_text(claim_text)`` (truncated). Same source +
    timestamp + (normalized) statement => same id => idempotent upsert + free dedup. The id is never
    supplied by the model.
    """
    basis = f"{source_video_id}|{int(timestamp_ms)}|{normalize_text(claim_text)}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()
    return f"clm_{digest[:16]}"
