"""AnthropicClaimExtractor — the REAL :class:`~knowledge_pipeline.ports.ClaimExtractor` (KNOW-05).

Claude does the extraction via **forced structured tool-use**: one tool (``emit_claims``) whose
``input_schema`` is :data:`~knowledge_pipeline.pure.extraction_schema.EXTRACTION_TOOL_SCHEMA`, forced with
``tool_choice={"type": "tool", "name": "emit_claims"}`` so the model MUST return a typed object instead of
free-form prose. That is the whole reliability argument: structure, not clever parsing. The careful,
versioned system prompt (:mod:`knowledge_pipeline.prompts`) supplies the discipline (atomic, cited,
extract-only, never invent numbers, calibrated confidence).

Model: ``claude-opus-4-8`` (current Opus; adaptive thinking is omitted on purpose — deterministic
extraction does not want exploratory reasoning, and forced tool-choice pairs cleanly with no-thinking).
Pricing for the cost note: ~$5.00 / 1M input, ~$25.00 / 1M output tokens (see README "Verification").

ENV-GATED / NOT RUN HERE: ``import anthropic`` is LAZY (inside ``__init__``), and the package never
imports this module eagerly — so the base install (pydantic + stdlib) imports and tests fine without the
SDK. Running it needs ``uv sync --extra extract`` + ``ANTHROPIC_API_KEY`` + real tokens.
"""

from __future__ import annotations

from typing import Iterable

from ..domain.claims import Claim
from ..domain.models import RawTranscript
from ..prompts import EXTRACTION_SYSTEM_PROMPT_V1, EXTRACTION_PROMPT_VERSION
from ..pure.extraction_schema import (
    EXTRACTION_TOOL_NAME,
    EXTRACTION_TOOL_SCHEMA,
    format_transcript_for_extraction,
    parse_extractor_output,
)


class AnthropicClaimExtractor:
    """Extract claims with Claude tool-use. Heavy import is LAZY; the call is env-gated."""

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-8",
        max_tokens: int = 8000,
        api_key: str | None = None,
    ) -> None:
        # LAZY heavy import — keeps the package importable + tests runnable without the SDK installed.
        import anthropic  # noqa: PLC0415  (intentional: env-gated leaf)

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self.prompt_version = EXTRACTION_PROMPT_VERSION

    def extract(self, transcript: RawTranscript, *, genres: Iterable[str] = ()) -> list[Claim]:
        """One transcript -> cited claims, via forced ``emit_claims`` tool-use. Env-gated (NOT run here)."""
        if not transcript.segments:
            return []

        genre_hint = ", ".join(genres) if genres else "(unspecified)"
        user_content = (
            f"Discovery genre context (only a hint — do not over-tag): {genre_hint}\n\n"
            f"TRANSCRIPT (each line: [mm:ss | <timestamp_ms>] text):\n\n"
            f"{format_transcript_for_extraction(transcript)}"
        )

        # Forced tool-use guarantees a typed `emit_claims` call. No `thinking` param: deterministic
        # extraction wants no exploratory reasoning, and forced tool_choice pairs cleanly with that.
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=EXTRACTION_SYSTEM_PROMPT_V1,
            tools=[
                {
                    "name": EXTRACTION_TOOL_NAME,
                    "description": "Emit every atomic, individually-cited production claim the transcript states.",
                    "input_schema": EXTRACTION_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": EXTRACTION_TOOL_NAME},
            messages=[{"role": "user", "content": user_content}],
        )

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == EXTRACTION_TOOL_NAME:
                raw = block.input if isinstance(block.input, dict) else {}
                return parse_extractor_output(raw, transcript, genres=list(genres))
        return []
