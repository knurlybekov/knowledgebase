"""Audit log table, the hardened SECURITY DEFINER audit trigger function, and
the access-event table.

The function runs as its owner (the migrator role), writes only allowlisted
columns, and uses a fixed search_path with pg_temp last, so a temporary table
created by the runtime role cannot shadow the audit table.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

CREATE_AUDIT_FN = r"""
CREATE OR REPLACE FUNCTION public.kb_audit_row_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    allowed text[] := pg_catalog.string_to_array(TG_ARGV[0], ',');
    org uuid; actor uuid; req text;
    target uuid; action text; diff jsonb;
BEGIN
    BEGIN org := NULLIF(pg_catalog.current_setting('app.org_id', true), '')::uuid; EXCEPTION WHEN others THEN org := NULL; END;
    BEGIN actor := NULLIF(pg_catalog.current_setting('app.actor_id', true), '')::uuid; EXCEPTION WHEN others THEN actor := NULL; END;
    BEGIN req := NULLIF(pg_catalog.current_setting('app.request_id', true), ''); EXCEPTION WHEN others THEN req := NULL; END;

    IF TG_OP = 'INSERT' THEN
        action := 'insert'; target := (NEW).id;
        SELECT pg_catalog.jsonb_object_agg(key, value) INTO diff
          FROM pg_catalog.jsonb_each(pg_catalog.to_jsonb(NEW)) WHERE key = ANY(allowed);
    ELSIF TG_OP = 'UPDATE' THEN
        action := 'update'; target := (NEW).id;
        SELECT pg_catalog.jsonb_build_object(
            'old', (SELECT pg_catalog.jsonb_object_agg(key, value) FROM pg_catalog.jsonb_each(pg_catalog.to_jsonb(OLD)) WHERE key = ANY(allowed)),
            'new', (SELECT pg_catalog.jsonb_object_agg(key, value) FROM pg_catalog.jsonb_each(pg_catalog.to_jsonb(NEW)) WHERE key = ANY(allowed)))
          INTO diff;
    ELSE
        action := 'delete'; target := (OLD).id;
        SELECT pg_catalog.jsonb_object_agg(key, value) INTO diff
          FROM pg_catalog.jsonb_each(pg_catalog.to_jsonb(OLD)) WHERE key = ANY(allowed);
    END IF;

    INSERT INTO public.infra_auditlog (id, organization_id, actor_id, request_id, action, target_table, target_id, diff, at)
    VALUES (pg_catalog.gen_random_uuid(), org, actor, req, action, TG_TABLE_NAME, target, COALESCE(diff, '{}'::jsonb), pg_catalog.now());
    RETURN COALESCE(NEW, OLD);
END;
$$;
REVOKE ALL ON FUNCTION public.kb_audit_row_change() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.kb_audit_row_change() TO kb_app;

CREATE OR REPLACE FUNCTION public.kb_audit_block_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'infra_auditlog is append-only';
END;
$$;
CREATE TRIGGER auditlog_immutable
BEFORE UPDATE OR DELETE ON public.infra_auditlog
FOR EACH ROW EXECUTE FUNCTION public.kb_audit_block_mutation();

-- The runtime role reads the log for administration; only the trigger writes it.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.infra_auditlog FROM kb_app;
GRANT SELECT ON public.infra_auditlog TO kb_app;
"""

DROP_AUDIT_FN = """
DROP TRIGGER IF EXISTS auditlog_immutable ON public.infra_auditlog;
DROP FUNCTION IF EXISTS public.kb_audit_block_mutation();
DROP FUNCTION IF EXISTS public.kb_audit_row_change() CASCADE;
"""

RLS_ACCESSEVENT = """
ALTER TABLE infra_accessevent ENABLE ROW LEVEL SECURITY;
ALTER TABLE infra_accessevent FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON infra_accessevent
    USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
"""
RLS_ACCESSEVENT_REVERSE = """
DROP POLICY IF EXISTS org_isolation ON infra_accessevent;
ALTER TABLE infra_accessevent NO FORCE ROW LEVEL SECURITY;
ALTER TABLE infra_accessevent DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("organization_id", models.UUIDField(db_index=True, null=True)),
                ("actor_id", models.UUIDField(db_index=True, null=True)),
                ("request_id", models.CharField(db_index=True, max_length=64, null=True)),
                ("action", models.CharField(max_length=16)),
                ("target_table", models.CharField(max_length=63)),
                ("target_id", models.UUIDField(null=True)),
                ("diff", models.JSONField()),
                ("at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ("-at",)},
        ),
        migrations.RunSQL(sql=CREATE_AUDIT_FN, reverse_sql=DROP_AUDIT_FN),
        migrations.CreateModel(
            name="AccessEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("search", "search"), ("answer", "answer"), ("tool_call", "tool_call"), ("document_read", "document_read"), ("investigation", "investigation"), ("denied", "denied")], max_length=20)),
                ("object_type", models.CharField(blank=True, default="", max_length=40)),
                ("object_id", models.CharField(blank=True, default="", max_length=64)),
                ("meta", models.JSONField(default=dict)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("investigation_id", models.UUIDField(db_index=True, null=True)),
                ("at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="organizations.organization")),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="accounts.user")),
            ],
            options={"ordering": ("-at",)},
        ),
        migrations.AddIndex(
            model_name="accessevent",
            index=models.Index(fields=["organization", "kind", "at"], name="infra_acces_organiz_338d58_idx"),
        ),
        migrations.RunSQL(sql=RLS_ACCESSEVENT, reverse_sql=RLS_ACCESSEVENT_REVERSE),
    ]
