"""Tool implementations. Each receives a verified Principal and the running
Investigation; each returns a JSON-serializable dict plus `_evidence` spans."""

from __future__ import annotations

from knowledge.api import DocumentVersion, visible_document, visible_versions
from retrieval.api import Chunk, search

from .auth import sanitize
from .errors import ToolError
from .urls_guard import safe_source_url

EXCERPT_CHARS = 500
DOCUMENT_WINDOW_CHARS = 8000
SOURCE_TYPES = {"google_drive", "sharepoint"}


def _result_item(r) -> dict:
    return {
        "evidence_id": r.evidence_id,
        "chunk_id": r.chunk_id,
        "document_id": r.document_id,
        "title": sanitize(r.title),
        "source_type": r.source_type,
        "source_url": safe_source_url(r.source_url, r.source_type),
        "version_label": r.version_label,
        "heading_path": [sanitize(h) for h in r.heading_path],
        "locator": r.locator,
        "excerpt": sanitize(r.excerpt[:EXCERPT_CHARS]),
    }


def search_knowledge(principal, investigation, args: dict) -> dict:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ToolError("invalid_argument", "query is required")
    source_types = [s for s in (args.get("source_types") or []) if s in SOURCE_TYPES]
    limit = max(1, min(int(args.get("limit") or 10), 20))
    results = search(
        principal, query[:1000], source_types=source_types or None, limit=limit, mode="deep"
    )
    evidence = [
        (r.chunk_id, r.version_id, r.locator.get("start_char", 0), r.locator.get("end_char", 0))
        for r in results
    ]
    return {"query": query, "results": [_result_item(r) for r in results], "_evidence": evidence}


def get_document(principal, investigation, args: dict) -> dict:
    document_id = str(args.get("document_id") or "").strip()
    if not document_id:
        raise ToolError("invalid_argument", "document_id is required")
    document = visible_document(principal, document_id)
    if document is None:
        raise ToolError("not_found", "no visible document with that id")
    version = visible_versions(principal).filter(document=document).order_by("-created_at").first()
    if version is None:
        raise ToolError("not_found", "no visible document with that id")
    text = version.content_text or ""
    sections = [
        {
            "index": i,
            "heading_path": s.get("heading_path", []),
            "locator": s.get("locator", {}),
            "chars": s.get("chars", 0),
        }
        for i, s in enumerate((version.structure or {}).get("sections", []))
    ]
    start = 0
    section = args.get("section")
    if section is not None:
        try:
            idx = int(section)
        except (TypeError, ValueError) as exc:
            raise ToolError("invalid_argument", "section must be an integer index") from exc
        if not 0 <= idx < len(sections):
            raise ToolError("invalid_argument", "section index out of range")
        start = sum(s["chars"] + 2 for s in sections[:idx])  # sections are joined with two newlines
    end = min(len(text), start + DOCUMENT_WINDOW_CHARS)
    window = sanitize(text[start:end])
    chunks = list(Chunk.objects.filter(version=version, is_active=True).order_by("position"))
    evidence = []
    evidence_ids = []
    for c in chunks:
        # Chunk text is a window over its section; report it as evidence when it overlaps the returned window.
        evidence.append(
            (
                str(c.id),
                str(version.id),
                c.locator.get("start_char", 0),
                c.locator.get("end_char", 0),
            )
        )
        evidence_ids.append(
            f"chunk:{c.id}@{version.version_label}[{c.locator.get('start_char', 0)}:{c.locator.get('end_char', 0)}]"
        )
    return {
        "document_id": str(document.id),
        "title": sanitize(document.title),
        "source_type": document.source_type,
        "source_url": safe_source_url(document.source_url, document.source_type),
        "version_label": version.version_label,
        "modified_at": document.modified_at_source.isoformat()
        if document.modified_at_source
        else None,
        "sections": sections,
        "window": {"start": start, "end": end, "total_chars": len(text)},
        "content": window,
        "evidence_ids": evidence_ids,
        "_evidence": evidence,
    }


def _version_or_none(version_id):
    return DocumentVersion.objects.filter(id=version_id).first()
