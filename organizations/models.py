"""Organizations and memberships. Organization has no RLS (it is resolved at
the request edge before the GUC is set); Membership has the organization policy
plus a SELECT-only self policy bound to app.actor_id."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    ROLE_MEMBER = "member"
    ROLE_STEWARD = "steward"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_MEMBER, "Member"),
        (ROLE_STEWARD, "Knowledge steward"),
        (ROLE_ADMIN, "Administrator"),
    ]
    STATUS_ACTIVE = "active"
    STATUS_REMOVED = "removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(
        max_length=16,
        choices=[(STATUS_ACTIVE, "Active"), (STATUS_REMOVED, "Removed")],
        default=STATUS_ACTIVE,
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="uniq_membership_org_user"
            )
        ]
        ordering = ("organization__name", "user__email")

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
