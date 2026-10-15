"""OpenAI composer with a JSON-schema response format. Not exercised by the
test suite (no key); the live marker test covers it when a key exists."""

from __future__ import annotations

import json

from .base import (
    SYSTEM_PROMPT,
    AnswerSchema,
    ComposerError,
    ComposerResult,
    EvidenceItem,
    render_evidence,
)

DEFAULT_MODEL = "gpt-5.5"


class OpenAIComposer:
    def __init__(self, *, api_key: str, model: str = "") -> None:
        if not api_key:
            raise ComposerError("OPENAI_API_KEY is empty")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model_id = model or DEFAULT_MODEL

    def answer(self, question: str, evidence: list[EvidenceItem]) -> ComposerResult:
        schema = AnswerSchema.model_json_schema()
        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\n{render_evidence(evidence)}",
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": schema, "strict": False},
                },
            )
            text = response.choices[0].message.content or "{}"
            parsed = AnswerSchema.model_validate(json.loads(text))
        except Exception as exc:
            raise ComposerError(f"openai:{type(exc).__name__}") from exc
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return ComposerResult(
            claims=parsed.claims,
            conflicts=parsed.conflicts,
            insufficient=parsed.insufficient,
            model_id=self.model_id,
            usage=usage,
        )
