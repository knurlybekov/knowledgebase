#!/bin/bash
# Runs once at first container start (empty data volume) as the POSTGRES_USER
# superuser. Creates two roles:
#
#   kb_migrator  owns the schema, runs migrations and the test suite
#                (CREATEDB for pytest-django test databases). No SUPERUSER,
#                no BYPASSRLS, so FORCE ROW LEVEL SECURITY binds it too.
#   kb_app       runtime role for web, worker, beat and knowledge-mcp.
#                No DDL, no TRUNCATE, no BYPASSRLS. Only SELECT, INSERT,
#                UPDATE, DELETE on application tables.
#
# Extensions and default privileges are installed in template1 as well, so a
# pytest-django test database inherits them.
set -euo pipefail

migrator_password="${KB_MIGRATOR_PASSWORD:-kb_migrator}"
app_password="${KB_APP_PASSWORD:-kb_app}"
migrator_sql="$(printf %s "$migrator_password" | sed "s/'/''/g")"
app_sql="$(printf %s "$app_password" | sed "s/'/''/g")"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE kb_migrator WITH LOGIN PASSWORD '${migrator_sql}' CREATEDB NOSUPERUSER NOBYPASSRLS NOCREATEROLE;
CREATE ROLE kb_app WITH LOGIN PASSWORD '${app_sql}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO kb_migrator, kb_app;
SQL

for db in "$POSTGRES_DB" template1; do
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO kb_migrator;
GRANT USAGE ON SCHEMA public TO kb_app;
ALTER DEFAULT PRIVILEGES FOR ROLE kb_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kb_app;
ALTER DEFAULT PRIVILEGES FOR ROLE kb_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO kb_app;
SQL
done
