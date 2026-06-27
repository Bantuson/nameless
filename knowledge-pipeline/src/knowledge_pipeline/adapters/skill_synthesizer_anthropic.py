"""AnthropicSkillSynthesizer — the REAL :class:`~knowledge_pipeline.ports.SkillSynthesizer` (KNOW-07).

Claude authors the layered skill via **forced structured tool-use**: one tool (``emit_skill``) whose
``input_schema`` is :data:`~knowledge_pipeline.pure.synthesis_schema.EMIT_SKILL_TOOL_SCHEMA`, forced with
``tool_choice={"type": "tool", "name": "emit_skill"}`` so the model returns a typed object, not prose. The
versioned system prompt (:data:`~knowledge_pipeline.prompts.SYNTHESIS_SYSTEM_PROMPT_V1`) supplies the
discipline (synthesize ONLY over the provided claims, never invent a number, cite everything by id), and
:func:`~knowledge_pipeline.pure.synthesis_schema.parse_synthesizer_output` re-grounds every citation from
the real claims so the model cannot fabricate a receipt. Even then the output is not trusted: the
pipeline runs the pure :func:`~knowledge_pipeline.pure.citation_gate.citation_gate` over it and REJECTS
anything not fully traceable — the model gets no special pass.

Model: ``claude-opus-4-8`` (current Opus; no ``thinking`` — synthesis here is constrained transformation
of a fixed evidence set, which forced tool-choice serves better than exploratory reasoning). Cost note for
the metered path: ~$5.00 / 1M input, ~$25.00 / 1M output tokens (see README "Verification").

ENV-GATED / NOT RUN HERE: ``import anthropic`` is LAZY (inside ``__init__``) and the package never imports
this module eagerly, so the base install (pydantic + stdlib) imports and tests fine without the SDK.
Running it needs ``uv sync --extra extract`` + ``ANTHROPIC_API_KEY`` + real tokens.
"""

from __future__ import annotations

from typing import Sequence

from ..domain.claims import ClaimCluster
from ..domain.skills import ProductionCell, SkillDraft
from ..prompts import SYNTHESIS_PROMPT_VERSION, SYNTHESIS_SYSTEM_PROMPT_V1
from ..pure.synthesis_schema import (
    EMIT_SKILL_TOOL_NAME,
    EMIT_SKILL_TOOL_SCHEMA,
    format_clusters_for_synthesis,
    parse_synthesizer_output,
)
from ..pure.synthesis_template import template_synthesize


class SynthesisError(RuntimeError):
    """Raised when the model returns no usable ``emit_skill`` payload (the pipeline records + skips)."""


class AnthropicSkillSynthesizer:
    """Author skills with Claude tool-use. Heavy import is LAZY; the call is env-gated."""

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-8",
        max_tokens: int = 4000,
        api_key: str | None = None,
    ) -> None:
        # LAZY heavy import — keeps the package importable + tests runnable without the SDK installed.
        import anthropic  # noqa: PLC0415  (intentional: env-gated leaf)

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self.prompt_version = SYNTHESIS_PROMPT_VERSION

    def synthesize(self, cell: ProductionCell, clusters: Sequence[ClaimCluster]) -> SkillDraft:
        """One cell -> a layered :class:`SkillDraft`, via forced ``emit_skill`` tool-use. Env-gated (NOT run here).

        The citations are re-grounded from the real claims by ``parse_synthesizer_output``; the result is
        still subject to the pure citation gate downstream. If the model returns nothing usable we fall back
        to the deterministic template over the SAME claims (never to an ungrounded guess) so a transient bad
        response cannot silently drop a cell.
        """
        clusters = list(clusters)
        user_content = (
            "Author ONE layered skill for this cell, synthesizing ONLY over the claims below. "
            "Cite every block by claim id; never invent a number.\n\n"
            f"{format_clusters_for_synthesis(cell, clusters)}"
        )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYNTHESIS_SYSTEM_PROMPT_V1,
            tools=[
                {
                    "name": EMIT_SKILL_TOOL_NAME,
                    "description": "Emit one layered production skill, synthesized only over the provided cited claims.",
                    "input_schema": EMIT_SKILL_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": EMIT_SKILL_TOOL_NAME},
            messages=[{"role": "user", "content": user_content}],
        )

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == EMIT_SKILL_TOOL_NAME:
                raw = block.input if isinstance(block.input, dict) else {}
                draft = parse_synthesizer_output(raw, cell, clusters, prompt_version=self.prompt_version)
                if draft is not None:
                    return draft
        # No usable structured output — fall back to the deterministic, fully-grounded template.
        return template_synthesize(cell, clusters)
