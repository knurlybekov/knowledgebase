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
    "connectors_connectorlink",
    "connectors_syncscope",
    "connectors_synclease",
    "connectors_syncrun",
    "connectors_changeinbox",
]
AUDIT = {
    "connectors_connectorlink": ["id", "organization_id", "user_id", "provider", "status", "status_changed_at", "last_error_code"],
    "connectors_syncscope": ["id", "organization_id", "link_id", "kind", "external_id", "last_ok_at", "current_reconcile_generation", "bootstrapped"],
    "connectors_syncrun": ["id", "organization_id", "scope_id", "kind", "status", "error_code", "reconcile_generation"],
}
CONSTRAINTS = [
    org_unique_sql("connectors_connectorlink"),
    org_unique_sql("connectors_syncscope"),
    composite_fk_sql("connectors_connectorlink", "organization_id, user_id", "organizations_membership", "organization_id, user_id", "link_membership_fk"),
    composite_fk_sql("connectors_syncscope", "organization_id, link_id", "connectors_connectorlink", "organization_id, id", "scope_link_org_fk"),
    composite_fk_sql("connectors_synclease", "organization_id, scope_id", "connectors_syncscope", "organization_id, id", "lease_scope_org_fk"),
    composite_fk_sql("connectors_syncrun", "organization_id, link_id", "connectors_connectorlink", "organization_id, id", "run_link_org_fk"),
    composite_fk_sql("connectors_syncrun", "organization_id, scope_id", "connectors_syncscope", "organization_id, id", "run_scope_org_fk"),
    composite_fk_sql("connectors_changeinbox", "organization_id, link_id", "connectors_connectorlink", "organization_id, id", "inbox_link_org_fk"),
    composite_fk_sql("connectors_changeinbox", "organization_id, scope_id", "connectors_syncscope", "organization_id, id", "inbox_scope_org_fk"),
]


class Migration(migrations.Migration):
    dependencies = [("connectors", "0001_initial"), ("infra", "0001_initial"), ("organizations", "0002_audit")]

    operations = [
        migrations.RunSQL(sql="".join(rls_policy_sql(t) for t in TABLES), reverse_sql="".join(rls_policy_reverse_sql(t) for t in TABLES)),
        migrations.RunSQL(sql="".join(audit_trigger_sql(t, c) for t, c in AUDIT.items()), reverse_sql="".join(audit_trigger_reverse_sql(t) for t in AUDIT)),
        migrations.RunSQL(sql="\n".join(CONSTRAINTS), reverse_sql=migrations.RunSQL.noop),
    ]
