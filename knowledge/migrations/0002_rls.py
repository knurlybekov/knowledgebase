from django.db import migrations

from infra.sql import (
    audit_trigger_reverse_sql,
    audit_trigger_sql,
    composite_fk_sql,
    org_unique_sql,
    rls_policy_reverse_sql,
    rls_policy_sql,
)

TABLES = [
    "knowledge_document",
    "knowledge_documentversion",
    "knowledge_accessgrant",
    "knowledge_documentreference",
]
AUDIT = {
    "knowledge_document": ["id", "organization_id", "source_type", "status", "generation", "tombstoned_at"],
    "knowledge_documentversion": ["id", "organization_id", "document_id", "version_label", "content_state", "content_hash"],
    "knowledge_accessgrant": ["id", "organization_id", "document_id", "version_id", "link_id", "scope_id", "revoked_at", "revoke_reason", "last_revalidated_at", "last_event_seq", "last_seen_reconcile_generation"],
}
CONSTRAINTS = [
    org_unique_sql("knowledge_document"),
    org_unique_sql("knowledge_documentversion"),
    "ALTER TABLE knowledge_documentversion ADD CONSTRAINT version_document_id_uniq UNIQUE (document_id, id);",
    composite_fk_sql("knowledge_documentversion", "organization_id, document_id", "knowledge_document", "organization_id, id", "version_document_org_fk"),
    composite_fk_sql("knowledge_accessgrant", "organization_id, document_id", "knowledge_document", "organization_id, id", "grant_document_org_fk"),
    composite_fk_sql("knowledge_accessgrant", "document_id, version_id", "knowledge_documentversion", "document_id, id", "grant_version_document_fk"),
    composite_fk_sql("knowledge_accessgrant", "organization_id, link_id", "connectors_connectorlink", "organization_id, id", "grant_link_org_fk"),
    composite_fk_sql("knowledge_accessgrant", "organization_id, scope_id", "connectors_syncscope", "organization_id, id", "grant_scope_org_fk"),
    composite_fk_sql("knowledge_documentreference", "organization_id, from_version_id", "knowledge_documentversion", "organization_id, id", "reference_version_org_fk"),
    composite_fk_sql("knowledge_documentreference", "organization_id, to_document_id", "knowledge_document", "organization_id, id", "reference_document_org_fk"),
]


class Migration(migrations.Migration):
    dependencies = [("knowledge", "0001_initial"), ("connectors", "0002_rls")]

    operations = [
        migrations.RunSQL(sql="".join(rls_policy_sql(t) for t in TABLES), reverse_sql="".join(rls_policy_reverse_sql(t) for t in TABLES)),
        migrations.RunSQL(sql="".join(audit_trigger_sql(t, c) for t, c in AUDIT.items()), reverse_sql="".join(audit_trigger_reverse_sql(t) for t in AUDIT)),
        migrations.RunSQL(sql="\n".join(CONSTRAINTS), reverse_sql=migrations.RunSQL.noop),
    ]
