# Knowledgebase

An organizational intelligence platform. It connects each member's own Google Drive or SharePoint account, indexes what that account can see, and answers questions with citations back to the files. A quick search returns a cited answer in seconds. A deep investigation runs an agent (Hermes) over several documents through read-only tools and reports what is documented, what conflicts, and what is not established. Documented decisions become records that a steward verifies.

Django 6.1 · PostgreSQL 17 with pgvector · Celery · HTMX · Tailwind v4 · Hermes Agent v0.22.1 (pinned) · MCP.

![Dashboard](docs/screenshots/02-dashboard.png)

## What it does

| Function | How it works | Verified |
|---|---|---|
| Connect a source | Each member links their own account (OAuth). The sync lists what the account can see, downloads supported formats, parses, chunks, and embeds them. Permissions are per member and revalidated every 12 hours. | Google Drive live on a 3,000-item drive; SharePoint and OneDrive mock-tested (see below) |
| Quick Search | Hybrid retrieval (vector plus full text) over the member's visible documents, then one model call that writes claims bound to passages. | Live |
| Deep Investigation | A Hermes agent gets one short-lived token and two read-only tools. It searches, reads, cross-references, and returns statements with evidence ids. Statements whose evidence was not returned to that run are set apart as unsupported. | Live, end to end through the web UI |
| Decision records | Passages from an answer or an investigation become a candidate record. A steward accepts it as draft, verifies it, or sends it back. A record is visible only to members who can see every passage behind it. | Live |
| Administration | Document counts, access freshness, sync scopes, the change inbox, and recent runs. | Live |
| Dark mode, keyboard, phone width | Theme follows the system and can be switched; every control is keyboard operable; pages stack at phone width. | Live |

All screenshots below were taken from the running app over the synthetic demo corpus (`eval/corpus/`). No real organizational content appears in this repository.

## Walkthrough

**Log in.** Local accounts; the demo organization ships with an admin, a steward, and a member.

![Login](docs/screenshots/01-login.png)

**Quick Search.** The answer's sentences carry numbered chips. The sources on the right carry the same numbers. Hover or focus a sentence and its source lights up, and back.

![Quick Search](docs/screenshots/03-quick-search.png)

**Deep Investigation.** The agent runs in its own process with a budget of turns, tool calls, characters, and time. The page polls while it runs and can cancel it.

![Investigation running](docs/screenshots/05-investigation-running.png)

The result is built from validated statements only. Each one cites the passage it rests on; conflicts and open questions get their own sections.

![Evidence linking](docs/screenshots/07-evidence-linking.png)

**Decision records.** Save the passages behind an answer as a candidate. A steward verifies it. The timeline shows which stages the evidence establishes and which it does not.

![Decision record](docs/screenshots/09-decision-verified.png)

**Investigations, decisions, accounts, administration.**

| | |
|---|---|
| ![Investigations](docs/screenshots/04-investigations.png) | ![Decisions](docs/screenshots/08-decisions.png) |
| ![Accounts](docs/screenshots/10-accounts.png) | ![Administration](docs/screenshots/11-administration.png) |

**Dark mode and phone width.**

| | |
|---|---|
| ![Dark mode](docs/screenshots/12-dark-mode.png) | ![Phone width](docs/screenshots/13-mobile.png) |

## The agent, seen from Hermes

Deep Investigation runs each question as one Hermes process with a generated configuration: one MCP server (this platform's knowledge server), a bearer token that lives only in that process, every other toolset disabled, memory off. The runner attests this configuration at startup by running a benign and an adversarial prompt against a self-check MCP server and refusing to serve if any non-knowledge tool is called.

Hermes also ships a web dashboard. It is not part of the deployment, but it is useful to watch the agent work with the same configuration. The MCP page shows the knowledge server registered with bearer auth, and the chat shows the tool calls the agent makes.

| | |
|---|---|
| ![Hermes MCP page](docs/screenshots/hermes-mcp.png) | ![Hermes chat with knowledge tool calls](docs/screenshots/hermes-chat.png) |

In the chat on the right the agent called `trace_decision` and `search_knowledge`, found nothing about a hosting decision in that account's drive, and said so instead of inventing an answer. The six tools it lists are the only ones it has.

To open the dashboard yourself, start it in the agent container with a password and the generated configuration pointing at the MCP server:

```bash
HASH=$(docker run --rm --entrypoint /opt/hermes/.venv/bin/python -w /opt/hermes kb-hermes-agent:dev \
  -c "from plugins.dashboard_auth.basic import hash_password; print(hash_password('choose-a-password'))")
docker compose --profile hermes run -d --no-deps --name kb-hermes-dash -p 127.0.0.1:9119:9119 \
  -v "$PWD/hermes/dashboard-config.yaml:/tmp/dash-src/config.yaml:ro" \
  -e HERMES_HOME=/tmp/dash -e KNOWLEDGE_MCP_TOKEN=<capability token of a running investigation> \
  -e HERMES_DASHBOARD_BASIC_AUTH_USERNAME=demo -e HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH="$HASH" \
  -e HERMES_DASHBOARD_BASIC_AUTH_SECRET="$(openssl rand -hex 24)" \
  --entrypoint sh hermes-agent -c 'mkdir -p /tmp/dash && cp /tmp/dash-src/config.yaml /tmp/dash/ && exec /opt/hermes/bin/hermes dashboard --host 0.0.0.0 --port 9119 --no-open'
```

`hermes/dashboard-config.yaml` is the configuration the runner generates per investigation (`hermes/runner/runs.py`, `render_config`), with the MCP URL of the development stack. The capability token must belong to a running investigation of the user whose documents the chat should see; the MCP server rejects anything else.

## Local development

```
cp .env.example .env            # fill SECRET_KEY, CONNECTOR_TOKEN_KEY (Fernet), RUNNER_SHARED_SECRET
make sync                       # uv sync (Python 3.14)
make up                         # postgres (127.0.0.1:5435) + redis (127.0.0.1:6381)
make migrate                    # as kb_migrator
make tailwind-build
make seed-demo                  # demo organization with synthetic documents
make run                        # web server; demo users: admin@/steward@/member@demo.invalid
make test                       # pytest on the compose Postgres
make eval                       # eval/results/<date>.md
```

One script starts the whole development stack with Deep Investigation on: `scripts/dev-up.sh`. It starts Postgres, Redis, migrations, demo data, the MCP server, the hermes-agent container, the Celery worker and beat, and the web server on http://localhost:8010. `scripts/dev-up.sh --stop` stops it. It needs `ANTHROPIC_API_KEY` in `.env` for the agent attestation.

Runtime processes use `DATABASE_URL` with the `kb_app` role; migrations and tests use `MIGRATOR_DATABASE_URL` (the Makefile does this).

## Connectors

**Google Drive.** Create an OAuth web client in Google Cloud with the Drive API enabled, scope `drive.readonly`, redirect URI `http://localhost:8010/connectors/google/callback/` for development (`https://<host>/connectors/google/callback/` in production). Put the client id and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. A Testing-mode consent screen works for the accounts you list as test users.

**SharePoint and OneDrive.** Register an app in Entra with platform Web, redirect URI `http://localhost:8010/connectors/microsoft/callback/`, delegated Microsoft Graph permissions `Files.Read.All` and, for work or school accounts, `Sites.Read.All`. Put `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, and `MICROSOFT_TENANT` (`organizations`, `consumers`, or `common`) in `.env`. With `consumers` or `common` the app asks only for `Files.Read.All`, because a personal account has no SharePoint permission.

A work or school tenant can block user consent for third-party apps. In that case the consent page shows an "approval required" message, and an administrator of that tenant must grant the app in Entra before anyone can link. This blocked the live SharePoint test for this project, so the Graph connector remains verified against mocked API responses only (`connectors/tests/`).

Each member links their own account; the platform indexes what that account can see, and other members see a document only when their own account can see it.

## Deep Investigation (Hermes)

```
make hermes-build               # builds hermes-base:v0.22.1 from the pinned tag, then the service image
docker compose --profile hermes up -d hermes-agent
make mcp                        # knowledge MCP server on :8710 (compose service knowledge-mcp in production)
make hermes-spike               # CLI contract checks
```

Set `HERMES_ENABLED=True`, `HERMES_MODEL`, the provider key named by `HERMES_PROVIDER_API_KEY_ENV`, `RUNNER_SHARED_SECRET`, `RUNNER_URL`, `KNOWLEDGE_MCP_URL`. Details, the live attestation results, and troubleshooting: `HERMES_INTEGRATION.md`.

## Production

`docker-compose.prod.yml` + `Caddyfile.example`. Only Caddy publishes ports. `web` migrates on start with `MIGRATOR_DATABASE_URL`; `worker`, `beat`, `knowledge-mcp` run as `kb_app`. Resource limits, health checks and restart policies are in the compose file. Set `DEBUG=False`, real `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, and strong `POSTGRES_PASSWORD`, `KB_MIGRATOR_PASSWORD`, `KB_APP_PASSWORD`.

### Backup and recovery

- Postgres: `docker compose -f docker-compose.prod.yml exec postgres pg_dump -U kb -Fc kb > backup.dump`; restore with `pg_restore -U kb -d kb --clean --if-exists backup.dump`. Roles are created by `scripts/postgres-init/` on an empty volume; on restore into a fresh volume run the init first, then `pg_restore`; the dump preserves owners (`kb_migrator`).
- Secrets live only in `.env` (never in the image: `.dockerignore`). Back up `.env` separately and rotate `CONNECTOR_TOKEN_KEY` by re-linking accounts.
- Redis holds queue and rate-limit state only; loss means pending tasks are re-enqueued by the beat scheduler and the reaper.
- Hermes data volume (`kb-hermes-data`) holds only transient run directories and terminal records; it needs no backup.

## Metrics

`GET /metrics` with `Authorization: Bearer <METRICS_TOKEN>` on the internal network.

## Documents

`ARCHITECTURE.md`, `SECURITY.md`, `HERMES_INTEGRATION.md`, `IMPLEMENTATION_STATUS.md`, `DECISIONS.md`, `CONTEXT.md`, `PRODUCT.md`, `DESIGN.md`, `PLAN.md`, `PLAN-REVIEW-LOG.md`.
