"""Public surface of the investigations app."""

from .models import CapabilityToken, Investigation, InvestigationEvidence
from .results import parse_result, validate_citations
from .runner_client import RunnerClient, RunnerError, RunState
from .service import (
    cancel_investigation,
    execute,
    get_investigation,
    investigator_instructions,
    mint_token,
    reap,
    start_investigation,
)


def org_urlpatterns() -> list:
    from .org_urls import urlpatterns

    return urlpatterns


__all__ = [
    "CapabilityToken",
    "Investigation",
    "InvestigationEvidence",
    "RunState",
    "RunnerClient",
    "RunnerError",
    "cancel_investigation",
    "execute",
    "get_investigation",
    "investigator_instructions",
    "mint_token",
    "org_urlpatterns",
    "parse_result",
    "reap",
    "start_investigation",
    "validate_citations",
]
