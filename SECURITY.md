# Security

## Trust boundaries

| Boundary | What crosses it | Control |
|---|---|---|
| Browser → `web` | session cookie, CSRF token, form and JSON bodies | Django auth, CSRF, pydantic validation, rate limits (login, search, investigations), security headers, HTTPS via Caddy |
| `web`/`worker` → Postgres | SQL as `kb_app` | RLS (`FORCE`) on every organization-scoped table, explicit organization predicates, composite FKs, no DDL/TRUNCATE for the runtime role, audit trigger `SECURITY DEFINER` with fixed `search_path` and column allowlist |
| `worker` → providers | OAuth refresh tokens (Fernet-encrypted at rest), delegated API calls | least-privilege read scopes (`drive.readonly`; `Files.Read.All`, `Sites.Read.All`), validated downloads (revision before/after, checksum), size caps |
| `web`/`worker` → runner | question, instructions, limits, capability token | `RUNNER_SHARED_SECRET` bearer, internal network only |
| runner → Hermes process | per-run `HERMES_HOME`, env with one capability token and the provider key | new process group, memory off, only `mcp-knowledge` toolset, attestation gate, directory erased at exit, orphan reconciliation with identity checks |
| Hermes → `knowledge-mcp` | MCP tool calls with the capability token | token hash lookup, scope entered before any scoped read, budgets reserved atomically, membership rechecked per call, evidence recorded per returned span, output envelope |
| documents → models | retrieved text | wrapped as data with a fixed notice, control characters stripped, lengths bounded; the agent instructions tell the model that documents are not instructions; the answer composer uses a system prompt with the same rule; nothing from document text is executed |

## Identity and isolation

- Organization isolation: RLS + explicit predicates (tests: `organizations/tests/test_rls.py`, `eval/test_rls_coverage.py`, `eval/test_runtime_role.py`).
- User isolation: visibility derives from the user's own delegated grants; cross-user and cross-organization tests in `mcp_server/tests/test_mcp_auth.py` and `knowledge/tests/test_pipeline.py`.
- Investigations: one Hermes process per investigation; no shared session store; the token is minted in the worker, never shown to the model, rotated on retry and revoked on every terminal transition, cancel, offboarding and deactivation.
- Offboarding: removing a membership or deactivating a user revokes links, grants, tokens and running investigations in one path (`organizations.api.remove_member`, `accounts/signals.py`).

## Data retention and deletion

- Source removal or loss of access → grant revoked → when no authorizing grant remains: chunks and embeddings deleted, version text nulled, references and decision-evidence excerpts nulled, answers and investigations purged of text (`knowledge/purge.py`), document tombstoned.
- Freshness: grants expire after 24 h without revalidation; the expiration sweeper purges versions whose grants are all stale beyond 24 h + 48 h.
- Runner: run directories (including the Hermes `state.db`) are erased at process exit; terminal records are erased on acknowledgment or after 24 h.
- Audit log: append-only, metadata only, no content columns.

## Known risks and limitations

- Visibility is "as of the last complete access revalidation", bounded by 24 h. A permission change at the source can take up to that long to take effect here. Incremental feeds apply explicit removals sooner.
- Runs share one container, uid and filesystem inside `hermes-agent`; isolation between concurrent runs is by process group and directory permissions, not by container.
- The provider key for the model is present in the `hermes-agent` container; organizational text goes to the configured inference provider. Configure the provider per the data-processing arrangement; Canadian residency is a deployment choice (provider, region), not solved in code.
- No SSO yet; local passwords with Django validators. No MFA.
- Hermes CLI behavior is verified by the spike for flags, config honoring, event protocol and exit codes; a full live run with tool calls and the attestation were not executed in this session (no provider key). The runner refuses runs until the attestation passes.
- Live connector behavior (real Google and Graph tenants) is mock-tested only.
- The rate limiter is a fixed window in Redis per user or IP; behind a proxy, `REMOTE_ADDR` is the proxy unless the proxy is trusted (not configured).
- `find_related_documents` similarity is embedding-based and labeled as a suggestion; with `EMBEDDER=mock` it is meaningless.

## Reporting

Security findings from the plan review and the post-build inspections, with their dispositions, are in `PLAN-REVIEW-LOG.md`.
