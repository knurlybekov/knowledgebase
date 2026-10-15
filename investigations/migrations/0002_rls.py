from django.db import migrations

from infra.sql import (
    audit_trigger_reverse_sql,
    audit_trigger_sql,
    composite_fk_sql,
    org_unique_sql,
    rls_policy_reverse_sql,
    rls_policy_sql,
)

# capabilitytoken is the global auth table: no RLS (looked up by hash before the scope is known).
TABLES = ["investigations_investigation", "investigations_investigationevidence"]
AUDIT = {
    "investigations_investigation": ["id", "organization_id", "user_id", "status", "content_state", "attempt", "run_key", "error_code", "tool_calls_used", "output_chars_used"],
    "investigations_capabilitytoken": ["id", "investigation_id", "organization_id", "user_id", "attempt", "expires_at", "revoked_at"],
}
CONSTRAINTS = [
    org_unique_sql("investigations_investigation"),
    composite_fk_sql("investigations_capabilitytoken", "investigation_id, user_id, organization_id", "investigations_investigation", "id, user_id, organization_id", "token_investigation_owner_fk"),
    composite_fk_sql("investigations_investigationevidence", "organization_id, investigation_id", "investigations_investigation", "organization_id, id", "evidence_investigation_org_fk"),
    composite_fk_sql("investigations_investigationevidence", "organization_id, chunk_id", "retrieval_chunk", "organization_id, id", "evidence_chunk_org_fk"),
    composite_fk_sql("investigations_investigationevidence", "version_id, chunk_id", "retrieval_chunk", "version_id, id", "evidence_chunk_version_fk"),
]


class Migration(migrations.Migration):
    dependencies = [("investigations", "0001_initial"), ("retrieval", "0002_rls"), ("infra", "0001_initial")]

    operations = [
        migrations.RunSQL(sql="".join(rls_policy_sql(t) for t in TABLES), reverse_sql="".join(rls_policy_reverse_sql(t) for t in TABLES)),
        migrations.RunSQL(sql="".join(audit_trigger_sql(t, c) for t, c in AUDIT.items()), reverse_sql="".join(audit_trigger_reverse_sql(t) for t in AUDIT)),
        migrations.RunSQL(sql="\n".join(CONSTRAINTS), reverse_sql=migrations.RunSQL.noop),
    ]
