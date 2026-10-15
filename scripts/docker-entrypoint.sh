#!/usr/bin/env sh
# web entrypoint: migrate as the migrator role, then serve as the runtime role.
# worker, beat and knowledge-mcp override the entrypoint in docker-compose.prod.yml.
set -e
if [ -n "${MIGRATOR_DATABASE_URL:-}" ]; then
  DATABASE_URL="$MIGRATOR_DATABASE_URL" python manage.py migrate --noinput
else
  echo "MIGRATOR_DATABASE_URL is not set; skipping migrate (runtime role has no DDL)." >&2
fi
exec "$@"
