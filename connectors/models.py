"""Per-user delegated connector links, sync scopes, leases, runs and the
durable change inbox (D3, ingestion pipeline steps 1-3)."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConnectorLink(models.Model):
    PROVIDER_GOOGLE = "google_drive"
    PROVIDER_SHAREPOINT = "sharepoint"
    PROVIDER_CHOICES = [(PROVIDER_GOOGLE, "Google Drive"), (PROVIDER_SHAREPOINT, "SharePoint")]
    STATUS_ACTIVE = "active"
    STATUS_ERROR = "error"
    STATUS_REVOKED = "revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="connector_links"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="connector_links"
    )
    identity = models.ForeignKey(
        "accounts.UserIdentity", on_delete=models.PROTECT, related_name="connector_links", null=True
    )
    provider = models.CharField(max_length=16, choices=PROVIDER_CHOICES)
    external_account_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    refresh_token_encrypted = models.BinaryField()
    oauth_scopes = models.JSONField(default=list)
    status = models.CharField(
        max_length=8,
        choices=[(STATUS_ACTIVE, "Active"), (STATUS_ERROR, "Error"), (STATUS_REVOKED, "Revoked")],
        default=STATUS_ACTIVE,
    )
    status_changed_at = models.DateTimeField(default=timezone.now)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    selected_scopes = models.JSONField(default=list)  # SharePoint: chosen sites and drives
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "provider", "external_account_id"],
                name="uniq_link_per_account",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.email or self.external_account_id}"


class SyncScope(models.Model):
    """One change feed: a Google account's changes feed, or one Graph drive."""

    KIND_GOOGLE_CHANGES = "google_changes"
    KIND_GRAPH_DRIVE = "graph_drive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    link = models.ForeignKey(ConnectorLink, on_delete=models.PROTECT, related_name="sync_scopes")
    kind = models.CharField(max_length=16)
    external_id = models.CharField(max_length=255, blank=True, default="")
    display_name = models.CharField(max_length=255, blank=True, default="")
    cursor_value = models.TextField(blank=True, default="")
    last_seq = models.BigIntegerField(default=0)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_reconcile_at = models.DateTimeField(null=True, blank=True)
    current_reconcile_generation = models.IntegerField(default=0)
    bootstrapped = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["link", "kind", "external_id"], name="uniq_scope_per_link"
            )
        ]


class SyncLease(models.Model):
    """Durable lease with a fencing token; one sync per scope at a time."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    scope = models.OneToOneField(SyncScope, on_delete=models.CASCADE, related_name="lease")
    lease_token = models.CharField(max_length=64, blank=True, default="")
    holder = models.CharField(max_length=128, blank=True, default="")
    expires_at = models.DateTimeField(default=timezone.now)


class SyncRun(models.Model):
    KIND_BOOTSTRAP = "bootstrap"
    KIND_INCREMENTAL = "incremental"
    KIND_RECONCILE = "full_reconcile"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    link = models.ForeignKey(ConnectorLink, on_delete=models.PROTECT, related_name="runs")
    scope = models.ForeignKey(SyncScope, on_delete=models.PROTECT, related_name="runs")
    kind = models.CharField(max_length=16)
    reconcile_generation = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, default=STATUS_RUNNING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    pages_done = models.IntegerField(default=0)
    changes_seen = models.IntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ("-started_at",)


class ChangeInbox(models.Model):
    """Durable change rows written with the cursor in one transaction."""

    KIND_UPSERT = "upsert"
    KIND_REMOVE = "remove"
    STATUS_PENDING = "pending"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_OBSOLETE = "obsolete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    link = models.ForeignKey(ConnectorLink, on_delete=models.PROTECT, related_name="+")
    scope = models.ForeignKey(SyncScope, on_delete=models.PROTECT, related_name="inbox")
    seq = models.BigIntegerField()
    source_id = models.CharField(max_length=512)
    kind = models.CharField(max_length=16)
    payload = models.JSONField(default=dict)
    observed_at = models.DateTimeField()
    reconcile_generation = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, default=STATUS_PENDING, db_index=True)
    attempts = models.IntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "seq"], name="uniq_inbox_seq")]
        ordering = ("seq",)
