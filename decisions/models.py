"""Organizational decision records (PLAN.md section 13). Candidate records come
from the agent or extraction; a steward verifies them. Visibility is evidence
bound: a reader sees a record only when every evidence revision is visible."""

import uuid

from django.db import models
from django.utils import timezone


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="projects"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "slug"], name="uniq_project_slug")
        ]

    def __str__(self) -> str:
        return self.name


class DecisionRecord(models.Model):
    STATUS_CANDIDATE = "candidate"
    STATUS_DRAFT = "draft"
    STATUS_VERIFIED = "verified"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (s, s) for s in (STATUS_CANDIDATE, STATUS_DRAFT, STATUS_VERIFIED, STATUS_SUPERSEDED)
    ]
    APPROVAL_DOCUMENTED = "documented"
    APPROVAL_UNDOCUMENTED = "undocumented"
    APPROVAL_UNKNOWN = "unknown"
    ORIGIN_AGENT = "agent"
    ORIGIN_USER = "user"
    ORIGIN_EXTRACTION = "extraction"
    CONTENT_PRESENT = "present"
    CONTENT_PURGED = "purged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="decisions"
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions"
    )
    title = models.CharField(max_length=300)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_CANDIDATE, db_index=True
    )
    content_state = models.CharField(max_length=8, default=CONTENT_PRESENT)
    decision_date = models.DateField(null=True, blank=True)
    recorded_rationale = models.TextField(null=True, blank=True)
    alternatives = models.JSONField(null=True, blank=True)  # [{text, evidence_ids}]
    participants = models.JSONField(null=True, blank=True)  # [str]
    approval_status = models.CharField(max_length=12, default=APPROVAL_UNKNOWN)
    superseded_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="supersedes"
    )
    origin = models.CharField(max_length=12, default=ORIGIN_USER)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True
    )
    verified_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title


class DecisionEvidence(models.Model):
    """A passage that supports one stage of the record. The chunk link is
    nullable so a purge leaves a durable tombstone (document, version label,
    position) without the text."""

    ROLE_CHOICES = [
        (r, r) for r in ("problem", "option", "decision", "rationale", "change", "status")
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    record = models.ForeignKey(DecisionRecord, on_delete=models.CASCADE, related_name="evidence")
    document = models.ForeignKey("knowledge.Document", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "knowledge.DocumentVersion", on_delete=models.PROTECT, related_name="+"
    )
    version_label = models.CharField(max_length=255)
    position = models.IntegerField(default=0)
    chunk = models.ForeignKey(
        "retrieval.Chunk", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default="decision")
    excerpt = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("created_at",)
