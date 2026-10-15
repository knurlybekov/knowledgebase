"""Grounded answers (PLAN.md "Retrieval and answers")."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from infra.api import record_access, with_org
from knowledge.api import versions_visible
from retrieval.api import SearchResult, search

from .composer.base import ComposerError, EvidenceItem
from .composer.factory import get_composer
from .models import Answer

log = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 24_000
EXCERPT_CHARS = 1200


@dataclass
class Citation:
    evidence_id: str
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    source_type: str
    source_url: str
    version_label: str
    locator: dict
    excerpt: str


@dataclass
class AnswerResult:
    id: str
    question: str
    evidence_state: str
    content_state: str
    claims: list[dict] = field(default_factory=list)  # {text, citations: [Citation]}
    unsupported: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    model_id: str = ""
    retrieval_meta: dict = field(default_factory=dict)
    withheld: bool = False

    @property
    def summary(self) -> str:
        if self.withheld:
            return (
                "This answer is no longer available: a document it relied on is not visible to you."
            )
        if self.evidence_state == Answer.STATE_INSUFFICIENT:
            return "The available documents do not establish an answer to this question."
        return " ".join(c["text"] for c in self.claims)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["summary"] = self.summary
        return data


def _locator_text(result: SearchResult) -> str:
    loc = result.locator
    for key in ("page", "slide", "sheet", "table"):
        if key in loc:
            return f"{key} {loc[key]}"
    return " / ".join(result.heading_path) if result.heading_path else ""


def _citation(result: SearchResult) -> Citation:
    return Citation(
        evidence_id=result.evidence_id,
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        version_id=result.version_id,
        title=result.title,
        source_type=result.source_type,
        source_url=result.source_url,
        version_label=result.version_label,
        locator=result.locator,
        excerpt=result.excerpt,
    )


def _bounded(results: list[SearchResult]) -> list[SearchResult]:
    out, used = [], 0
    for r in results:
        size = min(len(r.text), EXCERPT_CHARS)
        if used + size > MAX_CONTEXT_CHARS:
            break
        out.append(r)
        used += size
    return out


def answer_question(principal, question: str, *, source_types=None, k: int = 8) -> AnswerResult:
    question = (question or "").strip()
    results = _bounded(
        search(principal, question, source_types=source_types, limit=k, mode="quick")
    )
    citations = [_citation(r) for r in results]
    evidence = [
        EvidenceItem(
            index=i,
            title=r.title,
            excerpt=r.text[:EXCERPT_CHARS],
            locator_text=_locator_text(r),
            source_type=r.source_type,
        )
        for i, r in enumerate(results, start=1)
    ]
    claims: list[dict] = []
    unsupported: list[str] = []
    conflicts: list[str] = []
    model_id = ""
    usage: dict = {}
    if evidence:
        composer = get_composer()
        model_id = composer.model_id
        try:
            out = composer.answer(question, evidence)
        except ComposerError as exc:
            log.warning("composer failed", extra={"reason": str(exc)})
            out = None
        if out is not None:
            usage = out.usage
            conflicts = [str(c) for c in out.conflicts][:10]
            for claim in out.claims:
                valid = [i for i in claim.evidence_indices if 1 <= i <= len(citations)]
                if valid and claim.text.strip():
                    claims.append(
                        {
                            "text": claim.text.strip(),
                            "citations": [asdict(citations[i - 1]) for i in valid],
                        }
                    )
                elif claim.text.strip():
                    unsupported.append(claim.text.strip())
    if not claims:
        state = Answer.STATE_INSUFFICIENT
    elif conflicts:
        state = Answer.STATE_CONFLICTING
    else:
        state = Answer.STATE_SUFFICIENT
    meta = {
        "k": k,
        "retrieved": len(results),
        "source_types": list(source_types or []),
        "usage": usage,
    }
    version_ids = sorted({c.version_id for c in citations})
    with with_org(principal.organization_id, principal.user_id):
        # Publication-time recheck (D6): evidence revoked or purged while the
        # composer ran must not be disclosed, not even once.
        still_visible = versions_visible(principal, version_ids)
        if not still_visible:
            claims, unsupported, conflicts = [], [], []
            state = Answer.STATE_INSUFFICIENT
        row = Answer.objects.create(
            organization_id=principal.organization_id,
            user=principal.user,
            question=question,
            claims=claims,
            unsupported=unsupported,
            conflicts=conflicts,
            evidence_chunk_ids=[c.chunk_id for c in citations],
            evidence_version_ids=version_ids,
            evidence_state=state,
            retrieval_meta=meta,
            model_id=model_id,
            content_state=Answer.CONTENT_PRESENT if still_visible else Answer.CONTENT_PURGED,
        )
        record_access(
            principal.organization_id,
            principal.user,
            "answer",
            object_type="answer",
            object_id=row.id,
            meta={
                "evidence_state": state,
                "retrieved": len(results),
                "withheld": not still_visible,
            },
        )
    if not still_visible:
        return AnswerResult(
            id=str(row.id),
            question=question,
            evidence_state=state,
            content_state=row.content_state,
            withheld=True,
        )
    return AnswerResult(
        id=str(row.id),
        question=question,
        evidence_state=state,
        content_state=row.content_state,
        claims=claims,
        unsupported=unsupported,
        conflicts=conflicts,
        citations=citations,
        model_id=model_id,
        retrieval_meta=meta,
    )


def read_answer(principal, answer_id) -> AnswerResult | None:
    """Owner-only read with the D6 recheck over all supplied evidence."""
    with with_org(principal.organization_id, principal.user_id):
        row = Answer.objects.filter(
            id=answer_id, organization_id=principal.organization_id, user=principal.user
        ).first()
        if row is None:
            return None
        visible = row.content_state == Answer.CONTENT_PRESENT and versions_visible(
            principal, row.evidence_version_ids
        )
    if not visible:
        return AnswerResult(
            id=str(row.id),
            question=row.question,
            evidence_state=row.evidence_state,
            content_state=row.content_state,
            withheld=True,
        )
    citations = []
    seen = set()
    for claim in row.claims or []:
        for c in claim["citations"]:
            if c["chunk_id"] not in seen:
                seen.add(c["chunk_id"])
                citations.append(Citation(**c))
    return AnswerResult(
        id=str(row.id),
        question=row.question,
        evidence_state=row.evidence_state,
        content_state=row.content_state,
        claims=row.claims or [],
        unsupported=row.unsupported or [],
        conflicts=row.conflicts or [],
        citations=citations,
        model_id=row.model_id,
        retrieval_meta=row.retrieval_meta,
    )


def purge_answers_for_version(version) -> int:
    """Purge hook: every answer that saw this version loses its text."""
    return Answer.objects.filter(
        organization_id=version.organization_id, evidence_version_ids__contains=[str(version.id)]
    ).update(claims=None, unsupported=None, conflicts=None, content_state=Answer.CONTENT_PURGED)
