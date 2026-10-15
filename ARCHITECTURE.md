# Architecture

An organizational intelligence platform: it ingests documents from the accounts members link (Google Drive, SharePoint), indexes them with per-user, per-revision access grants, answers questions with citations, runs multi-step investigations through Hermes Agent over restricted MCP tools, and preserves documented decisions behind a steward workflow. Repository audit result: the starting point was an empty `django-admin startproject`; everything here was built in this project (see `PLAN.md`, `PLAN-REVIEW-LOG.md`, `DECISIONS.md`).

## Services

| Service | Image | Role | Network exposure |
|---|---|---|---|
| `web` | `Dockerfile` (python:3.14-slim, uv) | Django: UI, JSON endpoints, auth, organization scope | behind `caddy` only |
| `worker` | same | Celery: connector syncs, investigations, sweeps | internal |
| `beat` | same | static schedule: `schedule_syncs` 60 s, `expiration_sweep` 30 min, `reap_investigations` 30 s | internal |
| `knowledge-mcp` | same | MCP server (`manage.py run_mcp_server`), stateless streamable HTTP on 8710 | internal (`agents` network) |
| `hermes-agent` | `hermes/Dockerfile` FROM `hermes-base:v0.22.1` | runner (FastAPI 8700) that starts one Hermes process per investigation | internal (`agents` network) |
| `postgres` | `pgvector/pgvector:pg17` | data, RLS, vectors, full text | internal |
| `redis` | `redis:7-alpine` | Celery broker and cache (rate limits) | internal |
| `caddy` | `caddy:2-alpine` | TLS termination | 80/443 |

Django apps and their boundary (`<app>/api.py` is the only cross-app import surface; `eval/test_module_boundaries.py` enforces it):

`infra` (RLS helpers, audit, metrics, task base) · `accounts` (users, identities) · `organizations` (tenancy, memberships, middleware, Principal) · `connectors` (links, scopes, leases, inbox, providers, sync engine) · `knowledge` (documents, versions, grants, parsing, chunking, pipeline, purge, authorization predicates) · `retrieval` (chunks, embeddings, hybrid search) · `answers` (composer protocol, grounded answers) · `investigations` (Hermes lifecycle, tokens, evidence) · `mcp_server` (tool authorization unit, tools) · `decisions` (records, workflow, timeline, extraction, decision tools) · `web` (pages, JSON endpoints, administration) · `eval` (metrics, golden queries, invariant tests).

## Data flow

```
member links account ──OAuth (PKCE, state)──► ConnectorLink + UserIdentity + SyncScope
beat ─► sync_scope_task ─► SyncLease (fencing token)
   bootstrap: full listing ─► ChangeInbox rows + cursor (one fenced transaction per page)
   incremental: provider changes feed ─► ChangeInbox rows + cursor
   reconcile (every 12 h): full listing stamped with a generation ─► sweep not-seen grants after the barrier
process_inbox ─► knowledge.apply_change(link, scope, event, fetcher)
   phase 1 (short tx, document lock): Document, DocumentVersion, fast path refresh of AccessGrant(document, scope, version)
   phase 2 (no tx): validated download, parse, chunk, embed
   phase 3 (short tx, lock, generation check): chunks + embeddings + tsvector, grant upsert
   remove: revoke the scope's grant (or write a fence), purge the version when no authorizing grant remains
Quick Search: retrieval.search over visible_versions(principal) ─► Composer ─► claim validation ─► Answer (all supplied evidence recorded)
Deep Investigation: Investigation(queued) ─► worker claims, mints CapabilityToken, runner creates+starts Hermes ─► Hermes calls knowledge-mcp
   with the token ─► authorization unit (token → scope → budget → principal → tool → output allocation → evidence log)
   ─► result parsed, citations validated against InvestigationEvidence ─► completed (whole-object D6 on read)
Decision records: candidates from the agent (draft_knowledge_record), extraction, or a member ─► steward: draft → verified → superseded
```

## Authorization model

- Postgres RLS on every organization-scoped table (`FORCE`, policy on `app.org_id`), with `membership_self` for the pre-organization picker. Explicit `organization_id = principal.organization_id` predicates in every query are the first layer; RLS is the second.
- Two database roles: `kb_migrator` (owner, migrations, tests) and `kb_app` (runtime, no DDL, no TRUNCATE, no BYPASSRLS, no audit-log access).
- Visibility: `knowledge.authz.visible_versions(principal)` = versions with content whose `AccessGrant` is unrevoked, revalidated within `PERMISSION_FRESHNESS_MAX_AGE_S` (24 h), through an active link of the principal, for an active user with an active membership. Every read path (search, answers, MCP tools, UI, decision records) goes through it.
- Derived text follows its evidence (D6): answers and investigations record all supplied evidence and are withheld whole when any version becomes invisible; purge removes their text.
- Investigations: a per-investigation capability token (hashed, bound to user, organization, attempt) is the only identity the MCP server accepts; budgets (tool calls, output characters, deadline) are enforced with conditional updates inside the scoped transaction.

## Key engineering decisions

See `DECISIONS.md` (001 Hermes process per investigation; 002 local login + verified identity links; 003 per-user delegated grants bound to revisions with a freshness bound; 004 server-rendered UI; 005 short transactions and leases; 006 derived text follows evidence; 007 static beat schedule; 008 two database roles). The plan review that produced them, with the reviewer's objections and dispositions, is in `PLAN-REVIEW-LOG.md`.

## Observability

Structured JSON logs with `org_id`, `actor_id`, `request_id`, `investigation_id` (`infra/logging.py`). Prometheus metrics at `/metrics` (bearer `METRICS_TOKEN`): investigation attempts and terminal states, durations, tool calls and output characters, runner orphans reaped, access denials by path, grant revalidation age, overdue reconciles, sync checkpoints, inbox backlog, purges, lost leases. `AccessEvent` rows record searches, answers, tool calls, document reads and denials; the trigger-written `AuditLog` records allowlisted metadata changes.

## Evaluation

`make eval` (`manage.py run_eval`) ingests the synthetic corpus in `eval/corpus/` into a throwaway organization and scores `eval/golden.yaml`: recall@5, precision@5, MRR, evidence state, grounded claims (ordered-content-word proxy unless an LLM judge is configured), and the insufficient case. Results: `eval/results/<date>.md`. The agent path is evaluated through the in-process `FakeRunner` (end-to-end three-document test); live Hermes measurements require the image and a provider key (`pytest -m hermes`).
