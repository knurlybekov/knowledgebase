"""Parse the agent's fixed Markdown structure and validate citations against
the evidence the MCP server actually returned (PLAN.md "Hermes investigation
lifecycle")."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADINGS = ["Answer", "Evidence summary", "Conflicts", "Open questions", "Statements"]
_EVIDENCE_ID = re.compile(r"chunk:([0-9a-fA-F-]{36})@([^\[\]\s]+)\[(\d+):(\d+)\]")
_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ParsedResult:
    answer: str = ""
    evidence_summary: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    statements: list[dict] = field(default_factory=list)  # {text, evidence_ids}
    unsupported_statements: list[str] = field(default_factory=list)
    cited_evidence_ids: list[str] = field(default_factory=list)
    malformed: bool = False
    answer_verified: bool = False  # True only when at least one statement survived validation
    agent_prose: str = ""  # the agent's free-text answer, unverified


def _bullets(block: str) -> list[str]:
    items = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
        elif line and not items:
            items.append(line)
    cleaned = [i for i in items if i.lower().rstrip(".") not in {"none", "none found"}]
    return cleaned


def parse_result(text: str) -> ParsedResult:
    sections: dict[str, str] = {}
    matches = list(_HEADING.finditer(text or ""))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1).strip().lower()] = text[m.end() : end].strip()
    out = ParsedResult()
    if not sections or "answer" not in sections:
        out.malformed = True
        out.answer = (text or "").strip()[:4000]
        return out
    out.answer = sections.get("answer", "")[:4000]
    out.evidence_summary = _bullets(sections.get("evidence summary", ""))
    out.conflicts = _bullets(sections.get("conflicts", ""))
    out.open_questions = _bullets(sections.get("open questions", ""))
    for bullet in _bullets(sections.get("statements", "")):
        ids = [m.group(0) for m in _EVIDENCE_ID.finditer(bullet)]
        clean = _EVIDENCE_ID.sub("", bullet).replace("[]", "").strip(" []")
        # Removed citation markers leave separators behind ("text. , ."): collapse them.
        clean = re.sub(r"\s*,(\s*,)+", ",", clean)
        clean = re.sub(r"[\s,;]+$", "", clean).strip(" []")
        out.statements.append({"text": clean, "evidence_ids": ids})
    return out


def validate_citations(parsed: ParsedResult, returned_ids: set[str]) -> ParsedResult:
    """Statements whose evidence ids were not all returned by the MCP server to
    this investigation move to unsupported_statements. The presented Answer is
    built from the validated statements only; the agent's free-text answer is
    kept separately as unverified prose and never shown as a finding."""
    kept = []
    cited: list[str] = []
    for st in parsed.statements:
        valid = [i for i in st["evidence_ids"] if i in returned_ids]
        if valid and len(valid) == len(st["evidence_ids"]):
            kept.append(st)
            cited.extend(valid)
        else:
            parsed.unsupported_statements.append(st["text"])
    parsed.statements = kept
    parsed.cited_evidence_ids = sorted(set(cited))
    parsed.answer_verified = bool(kept)
    parsed.agent_prose = parsed.answer
    if kept:
        parsed.answer = " ".join(st["text"].rstrip(".") + "." for st in kept)
    else:
        parsed.answer = "The retrieved evidence does not establish a verifiable answer."
    return parsed
