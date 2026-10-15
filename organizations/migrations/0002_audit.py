"""Audit trigger on memberships (depends on the infra function)."""

from django.db import migrations

from infra.sql import audit_trigger_reverse_sql, audit_trigger_sql

TABLE = "organizations_membership"
COLUMNS = ["id", "organization_id", "user_id", "role", "status", "removed_at"]


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
        ("infra", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=audit_trigger_sql(TABLE, COLUMNS),
            reverse_sql=audit_trigger_reverse_sql(TABLE),
        ),
    ]
