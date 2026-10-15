"""Deterministic offline composer: word-overlap grounding for tests and dev."""

from __future__ import annotations

import re

from .base import Claim, ComposerResult, EvidenceItem

_WORD = re.compile(r"[a-zA-Z]{4,}")
_STOP = {
    "what",
    "when",
    "where",
    "which",
    "does",
    "have",
    "with",
    "that",
    "this",
    "from",
    "about",
    "were",
    "their",
    "there",
}


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)} - _STOP


def _first_sentence(text: str) -> str:
    body = text.split("\n", 1)[-1] if "\n" in text[:120] else text
    sentence = re.split(r"(?<=[.!?])\s+", body.strip(), maxsplit=1)[0]
    return sentence[:300]


class StubComposer:
    model_id = "stub"

    def answer(self, question: str, evidence: list[EvidenceItem]) -> ComposerResult:
        q = _terms(question)
        scored = []
        for item in evidence:
            overlap = len(q & _terms(item.excerpt))
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].index))
        claims = [
            Claim(text=_first_sentence(item.excerpt), evidence_indices=[item.index])
            for _, item in scored[:3]
        ]
        return ComposerResult(
            claims=claims, conflicts=[], insufficient=not claims, model_id=self.model_id
        )
