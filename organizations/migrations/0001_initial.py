"""Organization (no RLS) and Membership (organization policy + self policy)."""

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

MEMBERSHIP_SQL = """
ALTER TABLE organizations_membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations_membership FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON organizations_membership
    USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
-- Pre-organization self lookup: SELECT only, bound to the actor GUC.
CREATE POLICY membership_self ON organizations_membership FOR SELECT
    USING (user_id = NULLIF(current_setting('app.actor_id', true), '')::uuid);
"""
MEMBERSHIP_REVERSE = """
DROP POLICY IF EXISTS membership_self ON organizations_membership;
DROP POLICY IF EXISTS org_isolation ON organizations_membership;
ALTER TABLE organizations_membership NO FORCE ROW LEVEL SECURITY;
ALTER TABLE organizations_membership DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("member", "Member"), ("steward", "Knowledge steward"), ("admin", "Administrator")], default="member", max_length=16)),
                ("status", models.CharField(choices=[("active", "Active"), ("removed", "Removed")], default="active", max_length=16)),
                ("removed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to="organizations.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("organization__name", "user__email")},
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(fields=("organization", "user"), name="uniq_membership_org_user"),
        ),
        migrations.RunSQL(sql=MEMBERSHIP_SQL, reverse_sql=MEMBERSHIP_REVERSE),
    ]
