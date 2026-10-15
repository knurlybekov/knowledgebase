"""Small helpers shared by tests: organizations, users, memberships."""

import itertools

from accounts.models import User
from infra.api import with_org
from organizations.models import Membership, Organization

_seq = itertools.count(1)


def make_user(email: str | None = None, password: str = "correct-horse-battery-staple") -> User:
    n = next(_seq)
    return User.objects.create_user(email or f"user{n}@example.test", password)


def make_org(slug: str | None = None) -> Organization:
    n = next(_seq)
    slug = slug or f"org{n}"
    return Organization.objects.create(name=slug.title(), slug=slug)


def make_membership(
    org: Organization, user: User, role: str = Membership.ROLE_MEMBER
) -> Membership:
    with with_org(org.id, user.pk):
        return Membership.objects.create(organization=org, user=user, role=role)
