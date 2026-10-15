# Architecture decision records

Append-only. Supersede rather than delete. Format: `## NNN — Title (YYYY-MM-DD)` with Status, Context, Decision, Alternatives considered, Consequences. The plan review that shaped D1–D6 is in `PLAN-REVIEW-LOG.md`.

## 001 — One isolated Hermes process per investigation (2026-10-14)
**Status:** Accepted
**Context:** Hermes Agent v0.22.1 configures MCP servers statically in `config.yaml`; a run cannot carry the application user identity to MCP tool calls, and the API server shares one session store across callers.
**Decision:** A runner service inside the `hermes-agent` container starts one `hermes chat -q … --format stream-json` process per investigation with a generated `HERMES_HOME`, memory off, only the `mcp-knowledge` toolset, and the per-investigation capability token in that process's environment (`${KNOWLEDGE_MCP_TOKEN}` in the MCP header). The model never sees the token. The run directory is erased at exit; orphans are reconciled by pgid, start time and boot id. A configuration attestation against a self-check MCP server gates runs.
**Alternatives considered:** the Hermes API server (`/v1/runs`) with the token inside `instructions` (token in model context, shared session store); per-user Hermes profiles (one gateway per user, heavy).
**Consequences:** cold start per investigation; a runner we maintain; strongest isolation available with the documented surface. Build-time facts in `HERMES_INTEGRATION.md`.

## 002 — Local login plus verified identity links (2026-10-14)
**Status:** Accepted
**Context:** Source permissions name corporate identities; no tenant app registration was available for SSO.
**Decision:** Email-as-username users with Django sessions; `UserIdentity` rows written from the connector OAuth identity (`verified_via=oauth`) or asserted by an admin (`admin`). SSO later writes the same table.
**Alternatives considered:** OIDC-only now (mock-tested only); admin-asserted links only (weakest proof).
**Consequences:** login view changes later; data model stable.

## 003 — Per-user delegated connector credentials with revision-bound grants (2026-10-14)
**Status:** Accepted (owner's decision over the recommendation of organization-level credentials)
**Context:** Organization-level credentials need tenant-admin consent and ACL replication with group expansion.
**Decision:** Each user links their own Google or Microsoft account; the crawl runs as that user. `AccessGrant(document, scope, version)` records that this scope's crawl observed this revision. Storage dedupes by canonical source id and revision. Visibility is bounded: a grant is valid only when revalidated by an applied item event or a complete scope revalidation (every 12 h) within the last 24 h, the link is active, the user is active and the membership is active.
**Alternatives considered:** organization-level credentials + ACL replication; delegated as a later fallback.
**Consequences:** per-user API calls; documents reached only by a departed user's crawl go dark (fail closed); the promise is "as of the last complete access revalidation, at most 24 h old".

## 004 — Server-rendered UI with HTMX (2026-10-14)
**Status:** Accepted
**Decision:** Django templates + HTMX + Tailwind (standalone CLI). JSON endpoints under `/o/<slug>/api/v1/` for a later client. (Cosmetic deviation from the plan: `django-tailwind-cli` instead of `django-tailwind`, to keep Node out of the Django tree.)
**Alternatives considered:** React SPA + DRF.

## 005 — Short transactions with organization scope (2026-10-14, revised 2026-10-15)
**Status:** Accepted
**Decision:** `with_org()` opens one short transaction with `SET LOCAL app.org_id/app.actor_id`; external calls run between transactions. The request middleware sets session-level GUCs for the request and resets them; `ATOMIC_REQUESTS` is off. Syncs are serialized by a durable `SyncLease` with a fencing token; advisory locks are used only inside single short transactions per document.
**Consequences:** the Celery base class sets context only; every write is explicit.

## 006 — Derived text follows its evidence (2026-10-14)
**Status:** Accepted
**Decision:** Answers, investigation results and decision records are authorized against all evidence supplied to their generation; any loss withholds the whole object, any purge removes all text-bearing fields. Decision records are evidence-bound only; no organization-wide publication in this release. Publication-time rechecks run when an answer is saved, when an investigation completes and when a record is created or verified.

## 007 — Static Celery beat schedule (2026-10-14)
**Status:** Accepted
**Context:** `django-celery-beat` 2.9 pins Django below 6.1; the periodic tasks are fixed.
**Decision:** `CELERY_BEAT_SCHEDULE` in settings; no database scheduler.

## 008 — Two database roles (2026-10-14)
**Status:** Accepted
**Decision:** `kb_migrator` owns the schema and runs migrations and tests; `kb_app` runs the services with no DDL, no TRUNCATE, no BYPASSRLS and no access to the audit log. Every organization-scoped table has FORCE RLS; redundant relationships carry composite foreign keys; the audit trigger is `SECURITY DEFINER` with a fixed `search_path` and an allowlist of metadata columns.
