"""Anthropic composer through the official SDK with structured outputs."""

from __future__ import annotations

from .base import (
    SYSTEM_PROMPT,
    AnswerSchema,
    ComposerError,
    ComposerResult,
    EvidenceItem,
    render_evidence,
)

DEFAULT_MODEL = "claude-opus-5"


class AnthropicComposer:
    def __init__(self, *, api_key: str, model: str = "") -> None:
        if not api_key:
            raise ComposerError("ANTHROPIC_API_KEY is empty")
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model_id = model or DEFAULT_MODEL

    def answer(self, question: str, evidence: list[EvidenceItem]) -> ComposerResult:
        import anthropic

        try:
            response = self._client.messages.parse(
                model=self.model_id,
                max_tokens=4000,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\n{render_evidence(evidence)}",
                    }
                ],
                output_format=AnswerSchema,
            )
        except anthropic.APIError as exc:
            raise ComposerError(f"anthropic:{type(exc).__name__}") from exc
        if response.stop_reason == "refusal":
            raise ComposerError("anthropic:refusal")
        parsed = response.parsed_output
        if parsed is None:
            raise ComposerError("anthropic:no_parsed_output")
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return ComposerResult(
            claims=parsed.claims,
            conflicts=parsed.conflicts,
            insufficient=parsed.insufficient,
            model_id=self.model_id,
            usage=usage,
        )
