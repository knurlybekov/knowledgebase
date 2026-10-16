# Knowledgebase — organizational intelligence platform

Django 6.1 · PostgreSQL 17 + pgvector · Celery · Hermes Agent v0.22.1 (pinned) · MCP.

Documents: `ARCHITECTURE.md`, `SECURITY.md`, `HERMES_INTEGRATION.md`, `IMPLEMENTATION_STATUS.md`, `DECISIONS.md`, `CONTEXT.md`, `PLAN.md`, `PLAN-REVIEW-LOG.md`.

## Local development

```
cp .env.example .env            # fill SECRET_KEY, CONNECTOR_TOKEN_KEY (Fernet), RUNNER_SHARED_SECRET
make sync                       # uv sync (Python 3.14)
make up                         # postgres (127.0.0.1:5435) + redis (127.0.0.1:6381)
make migrate                    # as kb_migrator
make tailwind-build
make seed-demo                  # demo organization with synthetic documents
make run                        # http://localhost:8000 — demo users: admin@/steward@/member@demo.invalid
make test                       # pytest on the compose Postgres
make eval                       # eval/results/<date>.md
```

One script starts the whole development stack with Deep Investigation on (postgres, redis, migrations, demo data, MCP server, hermes-agent container, Celery worker with the threads pool, web server on :8010): `scripts/dev-up.sh`; `scripts/dev-up.sh --stop` stops it. It needs `ANTHROPIC_API_KEY` in `.env` for the agent attestation.

Runtime processes use `DATABASE_URL` with the `kb_app` role; migrations and tests use `MIGRATOR_DATABASE_URL` (the Makefile does this).

## Connectors

Set `GOOGLE_CLIENT_ID/SECRET` (OAuth web client, redirect URI `https://<host>/connectors/google/callback/`, scope `drive.readonly`) and `MICROSOFT_CLIENT_ID/SECRET/TENANT` (Entra app, redirect URI `https://<host>/connectors/microsoft/callback/`, delegated `Files.Read.All`, `Sites.Read.All`, `offline_access`). Each member links their own account; the platform indexes what that account can see.

## Deep Investigation (Hermes)

```
make hermes-build               # builds hermes-base:v0.22.1 from the pinned tag, then the service image
docker compose --profile hermes up -d hermes-agent
make mcp                        # knowledge MCP server on :8710 (compose service knowledge-mcp in production)
make hermes-spike               # CLI contract checks
```

Set `HERMES_ENABLED=True`, `HERMES_MODEL`, the provider key named by `HERMES_PROVIDER_API_KEY_ENV`, `RUNNER_SHARED_SECRET`, `RUNNER_URL`, `KNOWLEDGE_MCP_URL`. Details and troubleshooting: `HERMES_INTEGRATION.md`.

## Production

`docker-compose.prod.yml` + `Caddyfile.example`. Only Caddy publishes ports. `web` migrates on start with `MIGRATOR_DATABASE_URL`; `worker`, `beat`, `knowledge-mcp` run as `kb_app`. Resource limits, health checks and restart policies are in the compose file. Set `DEBUG=False`, real `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, and strong `POSTGRES_PASSWORD`, `KB_MIGRATOR_PASSWORD`, `KB_APP_PASSWORD`.

### Backup and recovery

- Postgres: `docker compose -f docker-compose.prod.yml exec postgres pg_dump -U kb -Fc kb > backup.dump`; restore with `pg_restore -U kb -d kb --clean --if-exists backup.dump`. Roles are created by `scripts/postgres-init/` on an empty volume; on restore into a fresh volume run the init first, then `pg_restore`, then `scripts/fix-table-ownership` is not needed because the dump preserves owners (`kb_migrator`).
- Secrets live only in `.env` (never in the image: `.dockerignore`). Back up `.env` separately and rotate `CONNECTOR_TOKEN_KEY` by re-linking accounts.
- Redis holds queue and rate-limit state only; loss means pending tasks are re-enqueued by the beat scheduler and the reaper.
- Hermes data volume (`kb-hermes-data`) holds only transient run directories and terminal records; it needs no backup.

## Metrics

`GET /metrics` with `Authorization: Bearer <METRICS_TOKEN>` on the internal network.
