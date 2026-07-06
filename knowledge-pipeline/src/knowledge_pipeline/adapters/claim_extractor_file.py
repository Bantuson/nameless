"""FileClaimExtractor — the REAL no-API :class:`~knowledge_pipeline.ports.ClaimExtractor` over pre-mined files.

The no-API-credits path (KNOW-05): Claude Code (in-session) mines claims file-to-file and drops one
``{video_id}.json`` per video into a directory; this adapter ingests them through the UNCHANGED
``MiningPipeline`` so ``verify_citation``, dedup, and cross-reference judge them exactly like API output.
Only the extraction leaf changes — the gate is identical.

The file shape IS the ``emit_claims`` tool input described by
:data:`~knowledge_pipeline.pure.extraction_schema.EXTRACTION_TOOL_SCHEMA`: a top-level JSON object with a
``claims`` array of ``{claim_text, technique, stage, genre?, stance?, timestamp_ms, quote, confidence}``
entries. No new shape is invented — the payload flows through the same
:func:`~knowledge_pipeline.pure.extraction_schema.parse_extractor_output` normalization as the live SDK
extractor, so the identity/citation fields (``source_video_id``, ``caption_source``) are bound from the
TRANSCRIPT and the quote's ``timestamp_ms`` is re-anchored to the real segment. A file can never spoof
identity fields or dodge re-anchoring; a mis-stated timestamp cannot poison the citation.

Stdlib-only (``json`` + ``pathlib`` + the pure schema module) — it joins the eagerly-imported adapter
family, unlike the live SDK extractor which stays lazy/unexported. This module imports no LLM SDK at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..domain.claims import Claim
from ..domain.models import RawTranscript
from ..pure.extraction_schema import parse_extractor_output

# Same-package private reuse is INTENTIONAL: one traversal guard for every video_id-becomes-a-path-component
# seam (P3 CR-01), never a second copy that can drift.
from .corpus_fs import _safe_video_id


class FileClaimExtractor:
    """Read one ``{video_id}.json`` of pre-mined claims per video; normalize via the pure schema path."""

    def __init__(self, mined_dir: Path | str) -> None:
        # No directory validation here on purpose — the CLI plane does that once with a friendly
        # message, and the adapter stays trivially constructible in tests.
        self._mined_dir = Path(mined_dir)
        self.calls: list[str] = []  # which videos were extracted (test assertions, mirrors the fake)

    def extract(self, transcript: RawTranscript, *, genres: Iterable[str] = ()) -> list[Claim]:
        """One transcript -> cited claims, read from ``<mined_dir>/<video_id>.json``.

        Error contract (leans on the UNCHANGED ``MiningPipeline``, which catches per-video extractor
        exceptions and records them as a skip-with-detail outcome — never a crash):

          * missing file    -> :class:`FileNotFoundError` naming the video id + expected path. This is a
            clear per-video skip in the mine report, and it stays distinguishable from a genuinely empty
            extraction (which would be ``extracted=0``, not an error detail).
          * malformed JSON  -> :class:`ValueError` naming the offending file (the loud error).
          * wrong top-level -> :class:`ValueError` naming the file and the expected shape.
        """
        self.calls.append(transcript.video_id)
        if not transcript.segments:
            # Mirrors the live SDK extractor: nothing to anchor citations against — no file is read.
            return []

        video_id = _safe_video_id(transcript.video_id)  # P3 CR-01: guard BEFORE any path composition
        path = self._mined_dir / f"{video_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no mined claims file for video {video_id!r}: expected {path} "
                f"(drop a {video_id}.json into the mined dir and re-run)"
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed mined claims JSON in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(
                f"mined claims file {path} has the wrong top-level type "
                f"({type(raw).__name__}): expected a JSON object with a 'claims' array "
                f"(the emit_claims tool input)"
            )

        # The exact same normalization/re-anchoring path as the live SDK extractor. Individually
        # malformed claim entries are skipped by the pure function per its existing contract —
        # no second validator here.
        return parse_extractor_output(raw, transcript, genres=list(genres))
