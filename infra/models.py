"""Audit log (trigger-written, immutable) and access events."""

import uuid

from django.db import models


class AuditLog(models.Model):
    """Written by the SECURITY DEFINER trigger `kb_audit_row_change` with an
    allowlist of metadata columns per table. Never content. No RLS: the
    organization column is set from the GUC for filtering by admins."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField(null=True, db_index=True)
    actor_id = models.UUIDField(null=True, db_index=True)
    request_id = models.CharField(max_length=64, null=True, db_index=True)
    action = models.CharField(max_length=16)
    target_table = models.CharField(max_length=63)
    target_id = models.UUIDField(null=True)
    diff = models.JSONField()
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-at",)


class AccessEvent(models.Model):
    """Application-written record of reads and tool calls. Organization-scoped."""

    KIND_CHOICES = [
        ("search", "search"),
        ("answer", "answer"),
        ("tool_call", "tool_call"),
        ("document_read", "document_read"),
        ("investigation", "investigation"),
        ("denied", "denied"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+", null=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    object_type = models.CharField(max_length=40, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    meta = models.JSONField(default=dict)
    request_id = models.CharField(max_length=64, blank=True, default="")
    investigation_id = models.UUIDField(null=True, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-at",)
        indexes = [models.Index(fields=["organization", "kind", "at"])]
