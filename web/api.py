"""Public surface of the web app: the shared rate limiter."""

from django.core.cache import cache


def _client_key(request) -> str:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"u:{user.pk}"
    return "ip:" + (request.META.get("REMOTE_ADDR") or "unknown")


def rate_limited(request, bucket: str, limit: int, window_s: int) -> bool:
    """Fixed-window counter in the cache. True when the caller is over the limit."""
    key = f"rl:{bucket}:{_client_key(request)}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=window_s)
        count = 1
    return count > limit


__all__ = ["rate_limited"]
