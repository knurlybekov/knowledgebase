"""Public surface of the answers app."""

from .composer.base import (
    SYSTEM_PROMPT,
    AnswerSchema,
    Claim,
    Composer,
    ComposerError,
    ComposerResult,
    EvidenceItem,
    render_evidence,
)
from .composer.factory import get_composer
from .composer.stub import StubComposer
from .models import Answer
from .service import AnswerResult, Citation, answer_question, read_answer

__all__ = [
    "SYSTEM_PROMPT",
    "Answer",
    "AnswerResult",
    "AnswerSchema",
    "Citation",
    "Claim",
    "Composer",
    "ComposerError",
    "ComposerResult",
    "EvidenceItem",
    "StubComposer",
    "answer_question",
    "get_composer",
    "read_answer",
    "render_evidence",
]
