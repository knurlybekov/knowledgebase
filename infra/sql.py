"""SQL fragments shared by migrations: RLS policies, audit triggers, composite
foreign keys. Every table-creating migration calls these so a new table never
ships without its policy."""


def rls_policy_sql(table: str) -> str:
    """ENABLE + FORCE row level security with the organization policy."""
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON {table}
    USING (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
"""


def rls_policy_reverse_sql(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS org_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


def audit_trigger_sql(table: str, columns: list[str]) -> str:
    """Attach the allowlisted audit trigger. `columns` are the metadata columns
    that may appear in the log; content columns are never listed."""
    cols = ",".join(columns)
    return f"""
CREATE TRIGGER audit_{table}
AFTER INSERT OR UPDATE OR DELETE ON {table}
FOR EACH ROW EXECUTE FUNCTION public.kb_audit_row_change('{cols}');
"""


def audit_trigger_reverse_sql(table: str) -> str:
    return f"DROP TRIGGER IF EXISTS audit_{table} ON {table};"


def org_unique_sql(table: str) -> str:
    """UNIQUE (organization_id, id) so children can reference the pair."""
    return f"ALTER TABLE {table} ADD CONSTRAINT {table}_org_id_uniq UNIQUE (organization_id, id);"


def composite_fk_sql(table: str, columns: str, parent: str, parent_columns: str, name: str) -> str:
    return (
        f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({columns}) "
        f"REFERENCES {parent} ({parent_columns}) DEFERRABLE INITIALLY DEFERRED;"
    )
