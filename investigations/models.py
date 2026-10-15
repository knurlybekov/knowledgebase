"""Investigations (Hermes runs), capability tokens and chunk-level evidence."""

import uuid

from django.db import models
from django.utils import timezone


class Investigation(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_DISPATCHED = "dispatched"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_TIMED_OUT = "timed_out"
    STATUS_INTERRUPTED = "interrupted"
    TERMINAL = {
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_CANCELLED,
        STATUS_TIMED_OUT,
        STATUS_INTERRUPTED,
    }
    CONTENT_PRESENT = "present"
    CONTENT_PURGED = "purged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="investigations"
    )
    question = models.TextField()
    status = models.CharField(max_length=12, default=STATUS_QUEUED, db_index=True)
    content_state = models.CharField(max_length=8, default=CONTENT_PRESENT)
    attempt = models.IntegerField(default=1)
    run_key = models.CharField(max_length=120, blank=True, default="")
    deadline_at = models.DateTimeField()
    dispatched_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_event_seq = models.IntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    activity = models.JSONField(default=list)
    usage = models.JSONField(default=dict)
    limits = models.JSONField(default=dict)
    tool_calls_used = models.IntegerField(default=0)
    output_chars_used = models.IntegerField(default=0)
    # Every revision any tool returned to the agent; independent of deletable evidence rows (D6).
    supplied_version_ids = models.JSONField(default=list, blank=True)
    # Every revision any tool returned to the agent; independent of deletable evidence rows (D6).
    error_code = models.CharField(max_length=64, blank=True, default="")
    status_detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["id", "user", "organization"], name="investigation_id_user_org_uniq"
            ),
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL


class CapabilityToken(models.Model):
    """Global auth table (no RLS): looked up by hash before the scope is known.
    One active token per investigation attempt; revoked on every terminal transition."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(max_length=64, unique=True)
    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="tokens"
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    attempt = models.IntegerField(default=1)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)


class InvestigationEvidence(models.Model):
    """A chunk span returned to the agent by a tool call. Citations must point here."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="evidence"
    )
    chunk = models.ForeignKey("retrieval.Chunk", on_delete=models.CASCADE, related_name="+")
    version = models.ForeignKey(
        "knowledge.DocumentVersion", on_delete=models.CASCADE, related_name="+"
    )
    span_start = models.IntegerField(default=0)
    span_end = models.IntegerField(default=0)
    returned_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["investigation", "chunk", "span_start", "span_end"],
                name="uniq_investigation_evidence",
            )
        ]
