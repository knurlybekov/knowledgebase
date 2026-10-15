"""The runtime role gets no direct access to the audit log; only the trigger writes it."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("infra", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql="REVOKE ALL ON public.infra_auditlog FROM kb_app;",
            reverse_sql="GRANT SELECT ON public.infra_auditlog TO kb_app;",
        ),
    ]
