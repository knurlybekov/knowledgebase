"""HTTP helpers: retry with exponential backoff and jitter, honoring Retry-After."""

from __future__ import annotations

import random
import time

import httpx

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


class ProviderError(Exception):
    def __init__(self, code: str, message: str = "", status: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.status = status


class AuthError(ProviderError):
    """Token refresh failed or the provider rejected the credential (401/403 on auth)."""


class ScopeLost(ProviderError):
    """The whole scope (drive) is gone or inaccessible (403/404 on the scope)."""


class ResyncRequired(ProviderError):
    """The cursor is no longer valid (Graph HTTP 410); a full re-enumeration is needed."""


def _sleep_for(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2**attempt + random.uniform(0, 0.5), 30.0)


def request_with_retry(
    client: httpx.Client, method: str, url: str, *, sleep=time.sleep, **kwargs
) -> httpx.Response:
    """Send a request, retrying 429 and 5xx with backoff. Raises ProviderError
    after MAX_ATTEMPTS. Non-retryable 4xx return normally for the caller to map."""
    last: httpx.Response | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise ProviderError("transport", str(exc)) from exc
            sleep(_sleep_for(attempt, None))
            continue
        if response.status_code not in RETRY_STATUSES:
            return response
        last = response
        if attempt < MAX_ATTEMPTS - 1:
            sleep(_sleep_for(attempt, response.headers.get("Retry-After")))
    assert last is not None
    raise ProviderError(
        "rate_limited" if last.status_code == 429 else "server_error", status=last.status_code
    )
