"""Retrieval and grounding metrics (PLAN.md section 17)."""

from __future__ import annotations

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


def claim_supported(claim_text: str, evidence_texts: list[str]) -> bool:
    """CI proxy for support: a normalized substring match, or at least 60% of the
    claim's content words appear in one evidence passage. An LLM judge replaces
    this behind EVAL_JUDGE; the proxy is labeled as such in the report."""
    claim = claim_text.lower().strip()
    if not claim:
        return False
    words = set(_WORD.findall(claim))
    for text in evidence_texts:
        low = text.lower()
        if claim[:120] in low:
            return True
        if words and len(words & set(_WORD.findall(low))) / len(words) >= 0.6:
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
