"""Stored answers. Derived text follows its evidence (D6)."""

import uuid

from django.db import models
from django.utils import timezone


class Answer(models.Model):
    STATE_SUFFICIENT = "sufficient"
    STATE_INSUFFICIENT = "insufficient"
    STATE_CONFLICTING = "conflicting"
    CONTENT_PRESENT = "present"
    CONTENT_PURGED = "purged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="answers")
    question = models.TextField()
    claims = models.JSONField(null=True, blank=True)  # [{text, evidence: [chunk_id, ...]}]
    unsupported = models.JSONField(null=True, blank=True)  # [text]
    conflicts = models.JSONField(null=True, blank=True)
    evidence_chunk_ids = models.JSONField(default=list)  # every chunk supplied to generation
    evidence_version_ids = models.JSONField(default=list)
    evidence_state = models.CharField(max_length=12)
    content_state = models.CharField(max_length=8, default=CONTENT_PRESENT)
    retrieval_meta = models.JSONField(default=dict)
    model_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("-created_at",)
