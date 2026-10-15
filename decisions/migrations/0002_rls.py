from django.db import migrations

from infra.sql import (
    audit_trigger_reverse_sql,
    audit_trigger_sql,
    composite_fk_sql,
    org_unique_sql,
    rls_policy_reverse_sql,
    rls_policy_sql,
)

TABLES = ["decisions_project", "decisions_decisionrecord", "decisions_decisionevidence"]
AUDIT = {
    "decisions_decisionrecord": ["id", "organization_id", "project_id", "status", "content_state", "approval_status", "origin", "created_by_id", "verified_by_id", "verified_at", "superseded_by_id"],
    "decisions_decisionevidence": ["id", "organization_id", "record_id", "document_id", "version_id", "role", "position"],
}
CONSTRAINTS = [
    org_unique_sql("decisions_decisionrecord"),
    org_unique_sql("decisions_project"),
    composite_fk_sql("decisions_decisionrecord", "organization_id, project_id", "decisions_project", "organization_id, id", "record_project_org_fk"),
    composite_fk_sql("decisions_decisionrecord", "organization_id, superseded_by_id", "decisions_decisionrecord", "organization_id, id", "record_superseded_org_fk"),
    composite_fk_sql("decisions_decisionevidence", "organization_id, record_id", "decisions_decisionrecord", "organization_id, id", "evidence_record_org_fk"),
    composite_fk_sql("decisions_decisionevidence", "organization_id, document_id", "knowledge_document", "organization_id, id", "decision_evidence_document_org_fk"),
    composite_fk_sql("decisions_decisionevidence", "document_id, version_id", "knowledge_documentversion", "document_id, id", "decision_evidence_version_document_fk"),
    composite_fk_sql("decisions_decisionevidence", "version_id, chunk_id", "retrieval_chunk", "version_id, id", "decision_evidence_chunk_version_fk"),
]


class Migration(migrations.Migration):
    dependencies = [("decisions", "0001_initial"), ("retrieval", "0002_rls"), ("infra", "0001_initial")]

    operations = [
        migrations.RunSQL(sql="".join(rls_policy_sql(t) for t in TABLES), reverse_sql="".join(rls_policy_reverse_sql(t) for t in TABLES)),
        migrations.RunSQL(sql="".join(audit_trigger_sql(t, c) for t, c in AUDIT.items()), reverse_sql="".join(audit_trigger_reverse_sql(t) for t in AUDIT)),
        migrations.RunSQL(sql="\n".join(CONSTRAINTS), reverse_sql=migrations.RunSQL.noop),
    ]
