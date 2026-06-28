"""``citation_gate`` — the PURE, hard citation-verification gate. The heart of Phase 5 (KNOW-08).

This is the programmatic answer to the project's central fear: an LLM synthesizing craft across many
sources will fabricate specificity, attach a real citation to a claim a source did not make, or launder a
conflict into a false consensus (PITFALLS #3). The two-pass design already bounds the synthesizer to the
extracted claim set; this gate is the *enforcement* — a draft that cannot be fully traced back to cited,
real, verbatim evidence is **REJECTED and never shipped**. "Quality in, quality out" stops being an
aspiration and becomes a check.

``citation_gate(draft, claims, *, snapshots=None) -> GateResult`` runs five pure rules over the structured
:class:`~knowledge_pipeline.domain.skills.SkillDraft` (NOT the rendered markdown — the gate certifies the
*content*; the emitter only decorates it with timestamps/ids afterwards):

  R1 UNCITED          — a section that asserts craft must cite ≥1 claim. No receipts -> reject.
  R2 NONEXISTENT_SRC  — every cited ``claim_id`` must exist in ``claims`` (no citation pointing at a
                        claim Phase 4 never extracted), and the citation's ``quote`` must equal the real
                        claim's quote (no quote tampering in the draft).
  R3 INVENTED_NUMBER  — every numeric value a section ASSERTS must appear in one of *that section's own*
                        cited source quotes. A confident value present in no cited quote ("40 Hz" when the
                        sources say 30) is the worst GIGO failure; this is the rule that catches it. Both
                        digit-form AND spelled-out cardinals are checked (WR-02), so "three hundred hertz"
                        cannot evade the rule; the residual word-number gaps are documented on
                        :func:`~knowledge_pipeline.domain.keys.word_numbers`.
  R4 UNGROUNDED       — the asserted prose must be covered (token overlap >= ``min_coverage``) by its
                        cited claims' text — catches hallucinated craft that smuggles no number.
  R5 CITATION_ROT     — (reuses Phase-4 :func:`~knowledge_pipeline.pure.citation.verify_citation`) when the
                        source ``snapshots`` are available, each cited claim's quote must still verify
                        against the snapshot it was mined from. Catches drift/takedown rot before ship.

Every failure is an auditable :class:`Rejection` (code + human detail + the offending section/claim), so a
reject is explainable, not a bare ``False``. The same primitives Phase 4 used (``normalize_text``,
``tokens``, ``numbers``, ``verify_citation``) are reused here — the gate is the consolidation of that
discipline, not a parallel re-implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from ..domain.claims import Claim
from ..domain.keys import normalize_text, numbers, tokens, word_numbers
from ..domain.models import RawTranscript
from ..domain.skills import SectionKind, SkillDraft, SkillSection
from .citation import verify_citation


class RejectionCode(str, Enum):
    """Why a draft failed the gate — one per rule (machine-actionable + human-readable)."""

    UNCITED = "uncited"                       # R1
    NONEXISTENT_SOURCE = "nonexistent_source" # R2 (missing claim id)
    QUOTE_TAMPERED = "quote_tampered"         # R2 (citation quote != the real claim's quote)
    INVENTED_NUMBER = "invented_number"       # R3
    UNGROUNDED_ASSERTION = "ungrounded_assertion"  # R4
    CITATION_ROT = "citation_rot"             # R5 (verify_citation failed against the snapshot)


@dataclass(frozen=True)
class Rejection:
    """One reason a draft was rejected — auditable, points at the offending section/claim."""

    code: RejectionCode
    detail: str
    section: Optional[str] = None    # the section's topic + kind, for the audit trail
    claim_id: Optional[str] = None


@dataclass(frozen=True)
class GateResult:
    """The verdict of :func:`citation_gate`. ``ok`` iff there are zero rejections (Pass vs Rejected)."""

    ok: bool
    rejections: tuple[Rejection, ...] = field(default_factory=tuple)

    @property
    def reasons(self) -> list[str]:
        """Compact ``code: detail`` strings — what the CLI/pipeline logs on a reject."""
        return [f"{r.code.value}: {r.detail}" for r in self.rejections]

    @property
    def codes(self) -> set[str]:
        return {r.code.value for r in self.rejections}


def _all_numbers(text: str) -> set[str]:
    """Every load-bearing numeric value a body asserts — digit-form AND spelled-out cardinals (WR-02). Pure."""
    return numbers(text) | word_numbers(text)


def _section_label(s: SkillSection) -> str:
    base = f"{s.kind.value}:{s.topic}"
    return f"{base}[{s.stance}]" if s.stance else base


def _is_assertive(s: SkillSection) -> bool:
    """A section 'asserts craft' iff its body has real content (whitespace-only blocks assert nothing)."""
    return bool(s.body and s.body.strip())


def citation_gate(
    draft: SkillDraft,
    claims: Mapping[str, Claim],
    *,
    snapshots: Optional[Mapping[str, RawTranscript]] = None,
    min_coverage: float = 0.6,
    citation_tolerance_ms: int = 2000,
) -> GateResult:
    """Run the five citation rules over ``draft``; return a Pass/Rejected verdict. Pure.

    Args:
        draft: the synthesizer's layered output (default + consensus + conflict sections).
        claims: the authoritative claim set (id -> :class:`Claim`) — the ONLY evidence a citation may
            point at. A citation to anything not in here is rejected (R2).
        snapshots: optional ``video_id -> RawTranscript`` for the deepest check (R5, reuses
            ``verify_citation``). When ``None`` the rot check is skipped (and noted nowhere — it is a
            strict *additional* check, never a way to pass).
        min_coverage: token-coverage floor for the ungrounded-assertion check (R4).
        citation_tolerance_ms: how far a cited quote may sit from its timestamp in R5 before it is drift.

    Returns:
        A :class:`GateResult`. ``ok`` only when no rule fires for any section.
    """
    rejections: list[Rejection] = []

    for section in draft.all_sections():
        if not _is_assertive(section):
            continue  # an honestly-empty block (e.g. "no contested topics") asserts nothing to verify
        label = _section_label(section)

        # ---- R1: an assertive section must cite something ----
        if not section.citations:
            rejections.append(
                Rejection(RejectionCode.UNCITED, "section asserts craft with no citation", section=label)
            )
            continue  # nothing to check the assertion against; later rules need citations

        # ---- R2: every citation must resolve to a real claim with the same quote ----
        cited_claims: list[Claim] = []
        bad_citation = False
        for cit in section.citations:
            claim = claims.get(cit.claim_id)
            if claim is None:
                rejections.append(
                    Rejection(
                        RejectionCode.NONEXISTENT_SOURCE,
                        f"cites claim '{cit.claim_id}' which is not in the extracted claim set",
                        section=label, claim_id=cit.claim_id,
                    )
                )
                bad_citation = True
                continue
            if normalize_text(cit.quote) != normalize_text(claim.quote):
                rejections.append(
                    Rejection(
                        RejectionCode.QUOTE_TAMPERED,
                        "citation quote does not match the cited claim's source quote",
                        section=label, claim_id=cit.claim_id,
                    )
                )
                bad_citation = True
                continue
            cited_claims.append(claim)
        if bad_citation or not cited_claims:
            continue  # the evidence base is unsound; do not run number/coverage checks on bad citations

        # ---- R3: no asserted number may be absent from a cited source quote ----
        # Digit-form AND spelled-out cardinals (WR-02): "three hundred hertz" is just as much an invented
        # value as "300 Hz", so both forms are extracted on each side and compared with the same set diff.
        # Evidence = the cited claims' quote AND claim_text (WR-03): R4's coverage check already unions both,
        # but R3 used quote-only — an asymmetry that false-rejected legitimate template skills (built from
        # claim_text) whenever an auto-caption garbled the number in the quote while claim_text carried it
        # clean. The two rules now agree on what "the evidence" is.
        asserted_numbers = _all_numbers(section.body)
        evidence_numbers: set[str] = set()
        for c in cited_claims:
            evidence_numbers |= _all_numbers(c.quote)
            evidence_numbers |= _all_numbers(c.claim_text)
        invented = asserted_numbers - evidence_numbers
        if invented:
            rejections.append(
                Rejection(
                    RejectionCode.INVENTED_NUMBER,
                    f"asserts number(s) {sorted(invented)} present in no cited source quote",
                    section=label,
                )
            )

        # ---- R4: the assertion must be covered by its cited claims (no hallucinated craft) ----
        if not _assertion_is_grounded(section.body, cited_claims, min_coverage):
            rejections.append(
                Rejection(
                    RejectionCode.UNGROUNDED_ASSERTION,
                    "asserted prose is not covered by any cited claim (possible hallucinated craft)",
                    section=label,
                )
            )

        # ---- R5: (optional, reuses verify_citation) each cited claim must still anchor in its snapshot ----
        if snapshots is not None:
            for c in cited_claims:
                snap = snapshots.get(c.source_video_id)
                if snap is None:
                    continue  # no snapshot to check against — skip (never a way to fail/pass on absence)
                chk = verify_citation(c, snap, tolerance_ms=citation_tolerance_ms)
                if not chk.ok:
                    rejections.append(
                        Rejection(
                            RejectionCode.CITATION_ROT,
                            f"cited claim no longer verifies against its snapshot ({chk.reason})",
                            section=label, claim_id=c.id,
                        )
                    )

    return GateResult(ok=not rejections, rejections=tuple(rejections))


def _assertion_is_grounded(body: str, cited_claims: list[Claim], min_coverage: float) -> bool:
    """True iff the body's content tokens are covered by the union of cited claim text/quotes. Pure.

    Mirrors ``verify_citation``'s coverage idea: we fold the body to normalized tokens and require that a
    sufficient fraction also appears across the cited claims' ``claim_text`` + ``quote``. The synthesizer
    builds bodies verbatim from claim_text, so a faithful draft scores ~1.0; hallucinated prose that no
    cited claim supports falls below ``min_coverage`` and is rejected.
    """
    body_tokens = [t for t in tokens(body) if not t.isdigit()]
    if not body_tokens:
        return True  # numbers-only / empty content — R3 already governs the numbers
    evidence: set[str] = set()
    for c in cited_claims:
        evidence |= set(tokens(c.claim_text))
        evidence |= set(tokens(c.quote))
    hits = sum(1 for t in body_tokens if t in evidence)
    return (hits / len(body_tokens)) >= min_coverage
