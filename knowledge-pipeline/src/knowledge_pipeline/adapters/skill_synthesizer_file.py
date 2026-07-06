"""FileSkillSynthesizer — the REAL no-API :class:`~knowledge_pipeline.ports.SkillSynthesizer` over pre-drafted files.

The no-API-credits path (KNOW-07/08), mirroring :mod:`~knowledge_pipeline.adapters.claim_extractor_file`:
Claude Code (in-session) authors skill drafts file-to-file and drops one ``{stage}__{genre}.json`` per
production cell into a directory; this adapter ingests them through the UNCHANGED ``SynthesisPipeline`` so
the pure ``citation_gate`` (R1–R5) judges them exactly like API output. A file-drafted skill gets no
special pass — a draft asserting an invented number or uncited prose is REJECTED identically. Only the
synthesizer leaf changes; the gate is identical.

The file shape IS the ``emit_skill`` tool input described by
:data:`~knowledge_pipeline.pure.synthesis_schema.EMIT_SKILL_TOOL_SCHEMA`: a top-level JSON object
``{name, description, default: {body, claim_ids, stance?}, sections: [{kind, topic, technique, stance?,
body, claim_ids}]}``. Citations are id REFERENCES only — no new shape is invented; the payload flows
through the same :func:`~knowledge_pipeline.pure.synthesis_schema.parse_synthesizer_output` normalization
as the live SDK synthesizer, so every citation's quote / timestamp / source is re-grounded from the REAL
claims and ids outside the cell are dropped. A file can never fabricate a quote/timestamp/source receipt.

Because ``SynthesisPipeline`` has NO per-cell error seam (unlike ``MiningPipeline``), a missing draft file
cannot become a per-cell skip by raising — the skip is implemented by SCOPING cell selection instead:
:func:`scope_clusters_to_cells` (and its store view :class:`CellScopedClaimStore`) trims each cluster's
genre list to genres whose ``(stage, genre)`` cell has a draft file, so the pipeline's own ``select_cells``
simply never visits a cell without one. Available cells author byte-identically to an unscoped run.

Stdlib-only (``json`` + ``pathlib`` + the pure schema module) — it joins the eagerly-imported adapter
family, unlike the live SDK synthesizer which stays lazy/unexported. This module imports no LLM SDK at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Collection, Sequence

from ..domain.claims import ClaimCluster
from ..domain.keys import normalize_key
from ..domain.skills import ProductionCell, SkillDraft
from ..pure.synthesis_schema import parse_synthesizer_output

#: Provenance stamp for file-drafted skills — ``skills show`` / audit reveal a draft's file origin.
FILE_DRAFT_PROMPT_VERSION = "file-draft-v1"


class DraftFileError(ValueError):
    """A PRESENT but unusable draft file: malformed JSON, wrong top-level type, or a payload that fails
    ``emit_skill`` validation / default re-grounding.

    FATAL by design — ``SynthesisPipeline`` has no per-cell error seam (any exception aborts the run), and
    a broken file's CONTENT is an authoring bug the user must fix, not a cell to silently drop. Missing
    files are the skip case (handled by selection scoping, see :func:`scope_clusters_to_cells`); broken
    files are the loud-abort case (the CLI converts this to a clean ``SystemExit`` naming the file).
    """


def draft_filename(cell: ProductionCell) -> str:
    """The draft file name for a cell: ``{normalize_key(stage)}__{normalize_key(genre)}.json``. Pure.

    WHY ``__``: ``normalize_key`` emits only lowercase kebab (``[a-z0-9-]``), so the double-underscore
    separator can never occur inside a key — the split is unambiguous even though stages AND genres
    contain hyphens (``deep-house``, ``alt-piano``, ``vocal-layering`` make any single-hyphen or
    slug-based scheme ambiguous: the cell slug ``deep-house-drums`` has two readings). Examples:
    ``vocal-layering__rnb.json``, ``drums__amapiano.json``, ``bassline__deep-house.json``.

    Path safety is by construction: the name is composed ONLY from ``normalize_key`` output
    (cluster-derived stage/genre labels), never raw user input, and ``[a-z0-9-]`` admits no separators
    or dot-dots.
    """
    return f"{normalize_key(cell.stage)}__{normalize_key(cell.genre)}.json"


class FileSkillSynthesizer:
    """Read one pre-drafted ``{stage}__{genre}.json`` per cell; normalize via the pure schema path."""

    def __init__(self, drafts_dir: Path | str) -> None:
        # No directory validation here on purpose — the CLI plane does that once with a friendly
        # message, and the adapter stays trivially constructible in tests.
        self._drafts_dir = Path(drafts_dir)
        self.calls: list[str] = []  # which cells were synthesized (test assertions, mirrors the fake)

    def draft_path(self, cell: ProductionCell) -> Path:
        """Where the cell's draft file must live — the CLI pre-scan and the error messages both use it."""
        return self._drafts_dir / draft_filename(cell)

    def has_draft(self, cell: ProductionCell) -> bool:
        """True iff a draft file exists for ``cell`` — the CLI plane's available-vs-skipped partition."""
        return self.draft_path(cell).exists()

    def synthesize(self, cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> SkillDraft:
        """One cell -> a layered :class:`SkillDraft`, read from ``<drafts_dir>/{stage}__{genre}.json``.

        Error contract:

          * missing file    -> :class:`FileNotFoundError` naming the cell slug + expected path. Under the
            ``--drafts-dir`` plane this is unreachable — selection is pre-scoped to cells WITH files (the
            skip seam) — it exists as defense-in-depth for direct/un-scoped use.
          * malformed JSON  -> :class:`DraftFileError` naming the offending file (the loud error).
          * wrong top-level -> :class:`DraftFileError` naming the file and the expected shape.
          * unusable payload-> :class:`DraftFileError` — the payload failed ``emit_skill`` validation or
            its default re-grounded to zero real citations. Explicitly NO template fallback (unlike the
            live SDK adapter): a fallback would author content the human never drafted.
        """
        self.calls.append(cell.slug)
        path = self.draft_path(cell)
        if not path.exists():
            raise FileNotFoundError(
                f"no skill draft file for cell {cell.slug!r}: expected {path} "
                f"(author the emit_skill payload to that filename and re-run)"
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DraftFileError(f"malformed skill draft JSON in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise DraftFileError(
                f"skill draft file {path} has the wrong top-level type ({type(raw).__name__}): "
                f"expected a JSON object matching the emit_skill tool input "
                f"(name/description/default/sections)"
            )

        # The exact same normalization/re-grounding path as the live SDK synthesizer. Individually-dropped
        # section citations are handled by the pure function per its existing contract — no second
        # validator here.
        draft = parse_synthesizer_output(
            raw, cell, list(clusters), prompt_version=FILE_DRAFT_PROMPT_VERSION
        )
        if draft is None:
            raise DraftFileError(
                f"skill draft file {path} is unusable: the payload failed emit_skill validation, or its "
                f"default re-grounded to zero real citations from this cell's claims (check the claim ids "
                f"and the default body). NOT falling back to the template — nothing the human never "
                f"drafted may be authored."
            )
        return draft


def scope_clusters_to_cells(
    clusters: Sequence[ClaimCluster], cells: Collection[ProductionCell]
) -> list[ClaimCluster]:
    """Trim each cluster's genre list to genres whose ``(stage, genre)`` cell is in ``cells``. PURE.

    This is the missing-file SKIP seam: the pipeline derives its cells from ``list_clusters()`` via the
    pure ``select_cells`` (a cell exists iff some cluster's genre list evidences it), so selecting over
    the scoped clusters can only yield the given cells — the UNCHANGED ``SynthesisPipeline`` simply never
    visits a cell without a draft file. The claims INSIDE clusters are untouched and an available cell's
    genre is kept in every cluster that had it, so available cells author byte-identically to an unscoped
    run. Clusters left with no genre are dropped; trimmed clusters are frozen-model copies
    (``model_copy``), never mutations of the inputs.
    """
    wanted = {(c.stage, c.genre) for c in cells}
    out: list[ClaimCluster] = []
    for cl in clusters:
        kept = [g for g in (cl.genre or []) if (cl.stage, g) in wanted]
        if not kept:
            continue
        out.append(cl if kept == list(cl.genre) else cl.model_copy(update={"genre": kept}))
    return out


class CellScopedClaimStore:
    """A thin READ-ONLY view over a ClaimStore that scopes ``list_clusters()`` to the given cells.

    The pipeline touches exactly two methods on its claim store: ``list_clusters()`` (scoped here via
    :func:`scope_clusters_to_cells` — the skip seam) and ``list_claims()`` (passed through UNFILTERED —
    the gate's authoritative claim index must stay COMPLETE, so R2/R5 run against the full evidence).
    Everything else delegates to the inner store via ``__getattr__``.
    """

    def __init__(self, inner, cells: Collection[ProductionCell]) -> None:
        self._inner = inner
        self._cells = list(cells)

    def list_clusters(self, **kwargs) -> list[ClaimCluster]:
        return scope_clusters_to_cells(self._inner.list_clusters(**kwargs), self._cells)

    def list_claims(self, **kwargs):
        # NEVER filtered: the gate's claim index is built from this — scoping it would weaken R2/R5.
        return self._inner.list_claims(**kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)
