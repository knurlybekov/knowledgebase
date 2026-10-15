"""Sprint 3 MCP tools: trace_decision, find_related_documents, draft_knowledge_record.
Each runs under the authorization unit of mcp_server (verified principal, budgets,
evidence recording). Items are labeled `confirmed` (quoted text from a verified
record), `recorded` (a candidate or draft record), or `inferred` (a search hit)."""

from __future__ import annotations

import re

from asgiref.sync import sync_to_async
from django.db.models import Q
from mcp.server.mcpserver import Context
from pgvector.django import CosineDistance

from investigations.api import InvestigationEvidence
from knowledge.api import DocumentReference, visible_document, visible_versions
from retrieval.api import Chunk, Embedding, get_embedder, search

from .models import DecisionEvidence, DecisionRecord
from .service import EvidenceInput, create_candidate, record_visible

_DATE = re.compile(
    r"\b(20\d{2}-\d{2}-\d{2}|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}|\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+20\d{2})\b"
)
CUES = "decided decision approved selected chose alternative instead proposal revised superseded replaced"


def _safe(text: str | None) -> str:
    from mcp_server.api import sanitize

    return sanitize(text or "")


def trace_decision(principal, investigation, args: dict) -> dict:
    from mcp_server.api import ToolError, delivered_evidence, safe_source_url

    topic = str(args.get("topic") or "").strip()
    if not topic:
        raise ToolError("invalid_argument", "topic is required")
    time_range = args.get("time_range") or None
    records = (
        DecisionRecord.objects.filter(
            organization_id=principal.organization_id, content_state=DecisionRecord.CONTENT_PRESENT
        )
        .filter(
            Q(title__icontains=topic)
            | Q(description__icontains=topic)
            | Q(evidence__excerpt__icontains=topic)
        )
        .distinct()
    )
    items = []
    evidence = []
    dependencies: set[str] = set()
    for record in records[:20]:
        ev = list(DecisionEvidence.objects.filter(record=record).select_related("document"))
        if not ev or not record_visible(principal, record):
            continue  # evidence-bound: cited and supplied revisions must all be visible
        # The record's prose may carry information from any supplied revision:
        # all of them become dependencies of the receiving investigation.
        dependencies.update(str(v) for v in (record.supplied_version_ids or []))
        record_evidence = []
        for e in ev:
            excerpt = _safe(e.excerpt)[:500]
            evidence_id = None
            if e.chunk_id:
                evidence_id, span = delivered_evidence(
                    e.chunk_id,
                    e.version_id,
                    e.version_label,
                    e.chunk.locator.get("start_char", 0),
                    excerpt,
                )
                evidence.append(span)
            record_evidence.append(
                {
                    "role": e.role,
                    "excerpt": excerpt,
                    "document_id": str(e.document_id),
                    "title": _safe(e.document.title),
                    "version_label": e.version_label,
                    "evidence_id": evidence_id,
                }
            )
        label = "confirmed" if record.status == DecisionRecord.STATUS_VERIFIED else "recorded"
        items.append(
            {
                "kind": "record",
                "label": label,
                "record_id": str(record.id),
                "status": record.status,
                "title": _safe(record.title),
                "decision_date": record.decision_date.isoformat() if record.decision_date else None,
                "approval_status": record.approval_status,
                "superseded_by": str(record.superseded_by_id) if record.superseded_by_id else None,
                "alternatives": record.alternatives or [],
                "rationale": _safe(record.recorded_rationale),
                "evidence": record_evidence,
            }
        )
    hits = search(principal, f"{topic} {CUES}", limit=10, mode="deep")
    hits = search(principal, f"{topic} {CUES}", limit=10, mode="deep")
    for r in hits:
        dates = sorted(set(_DATE.findall(r.text)))
        excerpt = _safe(r.excerpt)
        evidence_id, span = delivered_evidence(
            r.chunk_id, r.version_id, r.version_label, r.locator.get("start_char", 0), excerpt
        )
        items.append(
            {
                "kind": "passage",
                "label": "inferred",
                "evidence_id": evidence_id,
                "document_id": r.document_id,
                "title": _safe(r.title),
                "source_url": safe_source_url(r.source_url, r.source_type),
                "version_label": r.version_label,
                "excerpt": excerpt,
                "possible_dates": dates[:5],
            }
        )
        evidence.append(span)
    return {
        "topic": topic,
        "time_range": time_range,
        "items": items,
        "guidance": "confirmed = quoted evidence of a verified record; recorded = a candidate or draft awaiting review; "
        "inferred = a passage found by search. Dates are strings found in the text, not established facts.",
        "_evidence": evidence,
        "_dependency_versions": sorted(dependencies),
    }


def find_related_documents(principal, investigation, args: dict) -> dict:
    from mcp_server.api import ToolError, delivered_evidence, safe_source_url

    document_id = str(args.get("document_id") or "").strip()
    limit = max(1, min(int(args.get("limit") or 10), 20))
    document = visible_document(principal, document_id) if document_id else None
    if document is None:
        raise ToolError("not_found", "no visible document with that id")
    visible = visible_versions(principal)
    visible_doc_ids = set(visible.values_list("document_id", flat=True))
    visible_version_ids = set(visible.values_list("id", flat=True))
    explicit = []
    evidence = []
    # References are read only from revisions the reader may see, in both directions.
    for ref in DocumentReference.objects.filter(
        from_version__document=document, from_version_id__in=visible_version_ids
    ).select_related("to_document"):
        if ref.to_document_id in visible_doc_ids:
            explicit.append(
                {
                    "label": "explicit",
                    "kind": ref.kind,
                    "document_id": str(ref.to_document_id),
                    "title": _safe(ref.to_document.title),
                    "source_url": safe_source_url(
                        ref.to_document.source_url, ref.to_document.source_type
                    ),
                }
            )
            first = Chunk.objects.filter(version=ref.from_version).order_by("position").first()
            if first is not None:
                evidence.append(
                    (
                        str(first.id),
                        str(ref.from_version_id),
                        first.locator.get("start_char", 0),
                        first.locator.get("end_char", 0),
                    )
                )
    for ref in DocumentReference.objects.filter(
        to_document=document, from_version_id__in=visible_version_ids
    ).select_related("from_version__document"):
        src = ref.from_version.document
        if src.id in visible_doc_ids:
            explicit.append(
                {
                    "label": "explicit",
                    "kind": f"{ref.kind} (incoming)",
                    "document_id": str(src.id),
                    "title": _safe(src.title),
                    "source_url": safe_source_url(src.source_url, src.source_type),
                }
            )
            first = Chunk.objects.filter(version=ref.from_version).order_by("position").first()
            if first is not None:
                evidence.append(
                    (
                        str(first.id),
                        str(ref.from_version_id),
                        first.locator.get("start_char", 0),
                        first.locator.get("end_char", 0),
                    )
                )
    embedder = get_embedder()
    own = list(
        Embedding.objects.filter(
            chunk__document=document,
            chunk__version_id__in=visible_version_ids,
            model_id=embedder.model_id,
            model_version=embedder.model_version,
        ).values_list("vec", flat=True)[:20]
    )
    similar = []
    if own:
        dim = len(own[0])
        centroid = [sum(float(v[i]) for v in own) / len(own) for i in range(dim)]
        neighbours = (
            Embedding.objects.filter(
                organization_id=principal.organization_id,
                model_id=embedder.model_id,
                model_version=embedder.model_version,
                chunk__version_id__in=visible_version_ids,
            )
            .exclude(chunk__document=document)
            .annotate(distance=CosineDistance("vec", centroid))
            .order_by("distance", "chunk_id")[: limit * 4]
            .values_list("chunk_id", "distance")
        )
        seen = set()
        for chunk_id, distance in neighbours:
            chunk = Chunk.objects.select_related("document", "version").get(id=chunk_id)
            if chunk.document_id in seen:
                continue
            seen.add(chunk.document_id)
            excerpt = _safe(chunk.text[:300])
            evidence_id, span = delivered_evidence(
                chunk.id,
                chunk.version_id,
                chunk.version.version_label,
                chunk.locator.get("start_char", 0),
                excerpt,
            )
            similar.append(
                {
                    "label": "similar",
                    "document_id": str(chunk.document_id),
                    "title": _safe(chunk.document.title),
                    "source_url": safe_source_url(
                        chunk.document.source_url, chunk.document.source_type
                    ),
                    "distance": round(float(distance), 4),
                    "evidence_id": evidence_id,
                    "excerpt": excerpt,
                }
            )
            evidence.append(span)
            if len(similar) >= limit:
                break
    return {
        "document_id": str(document.id),
        "title": _safe(document.title),
        "explicit": explicit,
        "similar": similar,
        "guidance": "explicit = a reference recorded from the documents; similar = embedding similarity, a suggestion only.",
        "_evidence": evidence,
    }


def draft_knowledge_record(principal, investigation, args: dict) -> dict:
    """Create a CANDIDATE record from evidence the agent actually received. Draft only.
    The record depends on every revision the investigation saw, cited or not."""
    from mcp_server.api import ToolError

    topic = str(args.get("topic") or "").strip()
    record_type = str(args.get("record_type") or "decision")
    ids = [str(x) for x in (args.get("evidence_ids") or [])][:40]
    if not topic or not ids:
        raise ToolError("invalid_argument", "topic and evidence_ids are required")
    if record_type != "decision":
        raise ToolError("invalid_argument", "only record_type 'decision' is supported")
    if investigation.content_state != "present":
        raise ToolError(
            "not_running", "this investigation lost access to a source it read; drafting is refused"
        )
    returned = {
        f"chunk:{e.chunk_id}@{e.version.version_label}[{e.span_start}:{e.span_end}]": str(
            e.chunk_id
        )
        for e in InvestigationEvidence.objects.filter(investigation=investigation).select_related(
            "version"
        )
    }
    unknown = [i for i in ids if i not in returned]
    if unknown:
        raise ToolError(
            "invalid_argument",
            f"{len(unknown)} evidence ids were not returned to this investigation",
        )
    roles = args.get("roles") or {}
    evidence = [
        EvidenceInput(chunk_id=returned[i], role=str(roles.get(i, "decision"))) for i in ids
    ]
    supplied = [
        str(v)
        for v in InvestigationEvidence.objects.filter(investigation=investigation)
        .values_list("version_id", flat=True)
        .distinct()
    ]
    record = create_candidate(
        principal,
        title=topic[:300],
        evidence=evidence,
        origin=DecisionRecord.ORIGIN_AGENT,
        description=_safe(str(args.get("background") or ""))[:4000] or None,
        rationale=_safe(str(args.get("rationale") or ""))[:4000] or None,
        alternatives=args.get("alternatives") or None,
        approval_status=DecisionRecord.APPROVAL_UNKNOWN,
        supplied_version_ids=supplied,
    )
    return {
        "record_id": str(record.id),
        "status": record.status,
        "title": record.title,
        "note": "A candidate draft was created. A knowledge steward must verify it before it becomes authoritative. Nothing was published.",
        "_evidence": [],
    }


def register_mcp_tools(server, authorize_and_run) -> None:
    @server.tool(
        name="trace_decision",
        description="Trace a documented organizational decision: verified and candidate records with their evidence, plus passages found by search, each labeled confirmed, recorded or inferred.",
    )
    async def _trace(topic: str, ctx: Context, time_range: str | None = None) -> dict:
        return await sync_to_async(authorize_and_run, thread_sensitive=True)(
            ctx.headers,
            "trace_decision",
            {"topic": topic, "time_range": time_range},
            trace_decision,
        )

    @server.tool(
        name="find_related_documents",
        description="Documents related to one document: explicit references and embedding-similar documents, labeled separately.",
    )
    async def _related(document_id: str, ctx: Context, limit: int = 10) -> dict:
        return await sync_to_async(authorize_and_run, thread_sensitive=True)(
            ctx.headers,
            "find_related_documents",
            {"document_id": document_id, "limit": limit},
            find_related_documents,
        )

    @server.tool(
        name="draft_knowledge_record",
        description="Create a CANDIDATE decision record from evidence ids this investigation received. Draft only; a steward verifies it.",
    )
    async def _draft(
        topic: str,
        evidence_ids: list[str],
        ctx: Context,
        record_type: str = "decision",
        background: str | None = None,
        rationale: str | None = None,
    ) -> dict:
        args = {
            "topic": topic,
            "evidence_ids": evidence_ids,
            "record_type": record_type,
            "background": background,
            "rationale": rationale,
        }
        return await sync_to_async(authorize_and_run, thread_sensitive=True)(
            ctx.headers, "draft_knowledge_record", args, draft_knowledge_record
        )
