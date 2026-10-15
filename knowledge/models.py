"""Documents, revisions, per-link access grants and explicit references."""

import uuid

from django.db import models
from django.utils import timezone


class Document(models.Model):
    SOURCE_GOOGLE = "google_drive"
    SOURCE_SHAREPOINT = "sharepoint"
    SOURCE_CHOICES = [(SOURCE_GOOGLE, "Google Drive"), (SOURCE_SHAREPOINT, "SharePoint")]
    STATUS_ACTIVE = "active"
    STATUS_TOMBSTONE = "tombstone"
    STATUS_QUARANTINED = "quarantined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="documents"
    )
    source_type = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    # Canonical: gdrive:<fileId> or sp:<driveId>:<itemId>.
    source_id = models.CharField(max_length=512)
    source_url = models.URLField(max_length=2000, blank=True, default="")
    title = models.CharField(max_length=512, blank=True, default="")
    mime_type = models.CharField(max_length=255, blank=True, default="")
    path = models.CharField(max_length=2000, blank=True, default="")
    drive_id = models.CharField(max_length=255, blank=True, default="")
    site_id = models.CharField(max_length=255, blank=True, default="")
    author = models.CharField(max_length=255, blank=True, default="")
    created_at_source = models.DateTimeField(null=True, blank=True)
    modified_at_source = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default=STATUS_ACTIVE, db_index=True)
    generation = models.BigIntegerField(default=0)
    tombstoned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_type", "source_id"], name="uniq_document_source"
            )
        ]

    def __str__(self) -> str:
        return self.title or self.source_id


class DocumentVersion(models.Model):
    CONTENT_PRESENT = "present"
    CONTENT_PURGED = "purged"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    version_label = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64, blank=True, default="")
    content_text = models.TextField(null=True, blank=True)
    structure = models.JSONField(null=True, blank=True)
    parser = models.CharField(max_length=32, blank=True, default="")
    extracted_at = models.DateTimeField(null=True, blank=True)
    content_state = models.CharField(max_length=8, default=CONTENT_PURGED)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "version_label"], name="uniq_version_label")
        ]


class AccessGrant(models.Model):
    """This scope's crawl observed this revision of this document. A revoked
    grant with no version is a fence: a removal seen before any content was
    published, so an older staged publish cannot restore access."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="grants")
    version = models.ForeignKey(
        DocumentVersion, on_delete=models.PROTECT, related_name="grants", null=True, blank=True
    )
    link = models.ForeignKey(
        "connectors.ConnectorLink", on_delete=models.PROTECT, related_name="grants"
    )
    scope = models.ForeignKey(
        "connectors.SyncScope", on_delete=models.PROTECT, related_name="grants"
    )
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_revalidated_at = models.DateTimeField()
    last_event_seq = models.BigIntegerField(default=0)
    last_seen_reconcile_generation = models.IntegerField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "scope"], name="uniq_grant_document_scope")
        ]
        indexes = [models.Index(fields=["link", "revoked_at", "last_revalidated_at"])]


class DocumentReference(models.Model):
    KIND_EXPLICIT = "explicit_link"
    KIND_VERSION_OF = "version_of"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    from_version = models.ForeignKey(
        DocumentVersion, on_delete=models.CASCADE, related_name="references_out"
    )
    to_document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="references_in"
    )
    kind = models.CharField(max_length=16)
    evidence_excerpt = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_version", "to_document", "kind"], name="uniq_reference"
            )
        ]
