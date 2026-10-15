"""Public surface of the accounts app."""

from .models import User, UserIdentity


def link_identity(user, *, provider: str, external_id: str, email: str, verified_via: str) -> UserIdentity:
    """Create or refresh a verified identity row for this user. A provider
    identity belongs to exactly one platform user."""
    identity, _created = UserIdentity.objects.update_or_create(
        provider=provider,
        external_id=external_id,
        defaults={"user": user, "email": (email or "").lower(), "verified_via": verified_via},
    )
    return identity


__all__ = ["User", "UserIdentity", "link_identity"]
