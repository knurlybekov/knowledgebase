"""Retrieval and grounding metrics (PLAN.md section 17)."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-zA-Z]{4,}")


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float | None:
    if not relevant:
        return None
    top = retrieved[:k]
    return sum(1 for r in relevant if r in top) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float | None:
    if not relevant:
        return None
    top = retrieved[:k]
    return sum(1 for r in top if r in relevant) / max(1, len(top))


def mrr(retrieved: list[str], relevant: list[str]) -> float | None:
    if not relevant:
        return None
    for i, r in enumerate(retrieved, start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0


_NEG = re.compile(r"\b(not|no|never|none|cannot|n't|without|rejected|declined)\b")
_NUM = re.compile(
    r"\b\d+(?:[.,]\d+)?\b|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|fifty|hundred)\b"
)
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_STOP_PROXY = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "were",
    "was",
    "are",
    "for",
    "has",
    "have",
    "had",
    "its",
    "their",
    "then",
    "than",
    "into",
    "onto",
    "also",
}


def _negated(text: str) -> bool:
    return bool(_NEG.search(text.lower()))


def _ordered(words: list[str], sentence_words: list[str]) -> bool:
    pos = 0
    for w in words:
        try:
            pos = sentence_words.index(w, pos) + 1
        except ValueError:
            return False
    return True


def claim_supported(claim_text: str, evidence_texts: list[str]) -> bool:
    """CI proxy for support (labeled as a proxy in the report). A claim is
    supported when the evidence contains it as a normalized substring, or when
    every content word of the claim appears in one evidence sentence (or two
    consecutive sentences) in the same order, with the same negation polarity
    and the same numbers. Word order rejects reversed relations; the all-words
    rule rejects added qualifiers. An LLM judge (EVAL_JUDGE) replaces this when
    configured."""
    claim = " ".join(claim_text.lower().split()).rstrip(".")
    if not claim:
        return False
    words = [w for w in _WORD.findall(claim) if w not in _STOP_PROXY]
    numbers = set(_NUM.findall(claim))
    for text in evidence_texts:
        low = " ".join(text.lower().split())
        if claim in low:
            return True
        if not words:
            continue
        sentences = [x for x in _SENT.split(text.lower()) if x.strip()]
        windows = sentences + [a + " " + b for a, b in itertools.pairwise(sentences)]
        for window in windows:
            if (
                _ordered(words, _WORD.findall(window))
                and _negated(claim) == _negated(window)
                and numbers <= set(_NUM.findall(window))
            ):
                return True
    return False


@dataclass
class QueryResult:
    id: str
    mode: str
    retrieved: list[str]
    relevant: list[str]
    recall5: float | None
    precision5: float | None
    mrr: float | None
    evidence_state: str = ""
    claims: int = 0
    supported: int = 0
    unsupported_listed: int = 0
    expected_terms_hit: bool | None = None
    latency_ms: int = 0
    notes: list[str] = field(default_factory=list)
