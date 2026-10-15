"""Source URL validation: https only, provider host allowlist, no credentials."""

from urllib.parse import urlsplit

from django.conf import settings

_ALLOWED = {
    "google_drive": (
        "docs.google.com",
        "drive.google.com",
        "sheets.google.com",
        "slides.google.com",
    ),
    "sharepoint": (".sharepoint.com", ".sharepoint-df.com", ".sharepoint.us", "sharepoint.com"),
}


def safe_source_url(url: str, source_type: str) -> str:
    """Return the URL when it is https on an allowed host, else an empty string."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return ""
    extra = tuple(getattr(settings, "SOURCE_URL_ALLOWED_HOSTS", []) or [])
    allowed = _ALLOWED.get(source_type, ()) + extra
    for pattern in allowed:
        if pattern.startswith("."):
            if host.endswith(pattern) or host == pattern[1:]:
                return url
        elif host == pattern:
            return url
    return ""
