"""Public surface of the decisions app."""

from .extraction import extract_candidates_for_version
from .mcp_tools import (
    draft_knowledge_record,
    find_related_documents,
    register_mcp_tools,
    trace_decision,
)
from .models import DecisionEvidence, DecisionRecord, Project
from .service import (
    STAGES,
    EvidenceInput,
    Timeline,
    create_candidate,
    pending_approval_count,
    purge_records_for_version,
    record_visible,
    timeline,
    transition,
    visible_records,
)


def org_urlpatterns() -> list:
    from .org_urls import urlpatterns

    return urlpatterns


__all__ = [
    "STAGES",
    "DecisionEvidence",
    "DecisionRecord",
    "EvidenceInput",
    "Project",
    "Timeline",
    "create_candidate",
    "draft_knowledge_record",
    "extract_candidates_for_version",
    "find_related_documents",
    "org_urlpatterns",
    "pending_approval_count",
    "purge_records_for_version",
    "record_visible",
    "register_mcp_tools",
    "timeline",
    "trace_decision",
    "transition",
    "visible_records",
]
