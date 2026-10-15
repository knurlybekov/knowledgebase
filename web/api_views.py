"""JSON endpoints under /o/<slug>/api/v1/. Session-authenticated, CSRF-protected,
rate limited; bodies validated with pydantic."""

import json
from dataclasses import asdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from pydantic import ValidationError

from answers.api import answer_question
from retrieval.api import search

from .api import rate_limited
from .forms import AnswerRequest, SearchRequest


def _bad(errors) -> JsonResponse:
    return JsonResponse(
        {"error": "invalid_request", "details": json.loads(errors.json())}, status=400
    )


@login_required
@require_GET
def api_search(request):
    if rate_limited(request, "search", settings.RATE_LIMIT_SEARCH_PER_MIN, 60):
        return JsonResponse({"error": "rate_limited"}, status=429)
    try:
        req = SearchRequest(
            q=request.GET.get("q", ""),
            source_types=request.GET.getlist("source_types"),
            limit=int(request.GET.get("limit", 10)),
        )
    except (ValidationError, ValueError) as exc:
        return (
            _bad(exc)
            if isinstance(exc, ValidationError)
            else JsonResponse({"error": "invalid_request"}, status=400)
        )
    results = search(
        request.principal, req.q, source_types=req.source_types or None, limit=req.limit
    )
    return JsonResponse(
        {
            "results": [
                {k: v for k, v in asdict(r).items() if k != "text"} | {"evidence_id": r.evidence_id}
                for r in results
            ]
        }
    )


@login_required
@require_POST
def api_answer(request):
    if rate_limited(request, "search", settings.RATE_LIMIT_SEARCH_PER_MIN, 60):
        return JsonResponse({"error": "rate_limited"}, status=429)
    try:
        req = AnswerRequest.model_validate_json(request.body or b"{}")
    except ValidationError as exc:
        return _bad(exc)
    result = answer_question(
        request.principal, req.question, source_types=req.source_types or None, k=req.k
    )
    return JsonResponse(result.as_dict())
