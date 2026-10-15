from django.db import migrations

from infra.sql import audit_trigger_reverse_sql, audit_trigger_sql, rls_policy_reverse_sql, rls_policy_sql

TABLE = "answers_answer"
COLUMNS = ["id", "organization_id", "user_id", "evidence_state", "content_state", "model_id"]


class Migration(migrations.Migration):
    dependencies = [("answers", "0001_initial"), ("infra", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=rls_policy_sql(TABLE), reverse_sql=rls_policy_reverse_sql(TABLE)),
        migrations.RunSQL(sql=audit_trigger_sql(TABLE, COLUMNS), reverse_sql=audit_trigger_reverse_sql(TABLE)),
    ]
