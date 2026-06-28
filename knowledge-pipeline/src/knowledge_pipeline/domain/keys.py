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
# Sign-aware (WR-01): capture an optional leading minus so "-6 dB" (cut) and "6 dB" (boost) DON'T collapse
# to the same magnitude. The ``(?<![A-Za-z0-9])`` lookbehind keeps a hyphen that is a *connector* rather
# than a sign out of the capture — "TR-808" / "sub-808" yield ``808``, not ``-808`` — so only a real
# leading minus (preceded by start/space/punctuation) is read as negative.
_NUMBER = re.compile(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?")


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
    """Canonicalize a numeric token so ``030`` == ``30``, ``30.0`` == ``30``, ``-030`` == ``-30``. Pure.

    Sign-aware (WR-01): a leading minus is preserved (``-6`` stays ``-6``) so a sign flip cannot be grounded
    by the opposite-signed source, but ``-0`` canonicalizes to ``0`` (there is no negative zero magnitude).
    """
    neg = token.startswith("-")
    if neg:
        token = token[1:]
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    magnitude = token.lstrip("0") or "0"
    if magnitude == "0":
        return "0"
    return f"-{magnitude}" if neg else magnitude


def numbers(text: str) -> set[str]:
    """Every numeric token (int/decimal) in ``text``, canonicalized. Pure.

    The kernel of Phase 5's invented-number gate (KNOW-08): a producer parameter — ``300`` (Hz),
    ``-6`` (dB), ``120`` (BPM), ``808`` — is load-bearing craft. The gate extracts the numbers a skill
    *asserts* and demands every one of them also appear in a CITED source quote; a confident-sounding
    value present nowhere in the evidence ("high-pass at 40 Hz" when no source said 40) is the single
    worst GIGO failure, and surfacing it as a set difference makes the reject mechanical, not a judgment
    call. The unit travels in the prose, not the number — so "30 hz" in a quote grounds "30 Hz" in the
    skill, but a wrong magnitude never passes. Sign IS load-bearing for a mixing/EQ skill (WR-01): a leading
    minus is captured and preserved, so "+6 dB" (boost) is NOT grounded by "-6 dB" (cut) — a sign flip is a
    maximally-confident wrong value the gate must catch, not a rounding nuance.
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


def compute_claim_id(
    source_video_id: str,
    timestamp_ms: int,
    claim_text: str,
    *,
    stance: str | None = None,
    technique: str | None = None,
) -> str:
    """Deterministic, content-addressed claim id. Pure.

    sha1 over ``video_id | timestamp_ms | normalize_text(claim_text) | stance | technique`` (truncated).
    Same source + timestamp + (normalized) statement + stance + technique => same id => idempotent
    upsert + free dedup. The id is never supplied by the model.

    ``stance`` (and ``technique``) are part of the identity basis so two claims from the same source at
    the same timestamp with identical text but OPPOSING stance (e.g. "boost 2 kHz" vs "cut 2 kHz") get
    DISTINCT ids and can never silently collapse into one — preserving a same-source conflict instead of
    laundering it away.
    """
    basis = (
        f"{source_video_id}|{int(timestamp_ms)}|{normalize_text(claim_text)}"
        f"|{normalize_key(stance)}|{normalize_key(technique)}"
    )
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()
    return f"clm_{digest[:16]}"
