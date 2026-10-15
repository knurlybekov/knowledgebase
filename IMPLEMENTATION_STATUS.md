# Implementation status (2026-10-15)

Repository audit result: the "existing application" was an empty `django-admin startproject`; the platform was built here from the plan in `PLAN.md`, which survived four rounds of adversarial review (`PLAN-REVIEW-LOG.md`). Patterns were copied from the author's EMPlanPlatform repository; nothing is imported from it.

## Test results

`make test` on the compose Postgres (kb_migrator role, real RLS): **111 passed, 1 skipped** (the skipped test is the live Hermes attestation, which needs a provider key). Lint (`ruff`) clean. Live markers: `pytest -m hermes` (needs `kb-hermes-agent:dev` and `ANTHROPIC_API_KEY`), `pytest -m live` (provider calls).

Evaluation (`make eval`, mock embedder, stub composer, synthetic corpus): `eval/results/2026-10-15.md`. Quick queries: recall@5 = 1.00 and MRR ≥ 0.5 on the three answerable ones through the keyword path; the unanswerable query returns `insufficient`; stub claims pass the support proxy (normalized substring or ≥80% word overlap with matching negation and numbers). Deep queries run through the real investigation lifecycle with the in-process FakeRunner driving the MCP tools: all three complete with recall@5 = 1.00 over the relevant documents and every statement cites evidence that was returned to the investigation (the statements themselves are the scripted fake's excerpt sentences, not model output). Vector-leg quality, LLM-judged grounding and live Hermes behavior are not measured without provider keys.

## Acceptance criteria

| Criterion | State | Evidence |
|---|---|---|
| An authorized user can connect a supported knowledge source | implemented, mock-verified | OAuth flows for Google (PKCE, offline) and Microsoft (MSAL); `connectors/tests/test_oauth_views.py`. **Blocked for live use:** no Google OAuth client or Entra app registration in this session. |
| Documents can be ingested and indexed | verified | parsers (docx, pptx, xlsx, pdf, text/markdown), chunker, publish with tsvector + halfvec; `knowledge/tests/`, `connectors/tests/test_sync_engine.py` |
| Incremental changes synchronize correctly | verified against in-memory providers | Google bootstrap + changes replay, Graph delta, cursors checkpointed with inbox rows, leases with fencing, reconcile barrier with supersession; `connectors/tests/test_sync_engine.py`. **Not run against real tenants.** |
| Deleted or inaccessible documents stop appearing | verified | removal, scope loss, link error, deselection, deactivation, expiration sweep, fences; `knowledge/tests/test_pipeline.py`, `test_inspection_fixes.py` |
| Search respects source permissions | verified | per-scope revision grants, freshness bound, membership and user checks, RLS + explicit predicates; `retrieval/tests`, `eval/test_runtime_role.py` |
| Standard RAG returns grounded answers with citations | verified with the stub composer | claim validation, unsupported statements separated, insufficient state, D6 withholding, publication-time recheck; `answers/tests`. Anthropic adapter (`messages.parse`, structured output) and OpenAI adapter exist but **were not exercised against a provider**. |
| Hermes executes multi-step investigations through restricted MCP tools | implemented; agent path verified with an in-process FakeRunner; Hermes CLI verified by spike only | runner, attestation, lifecycle, budgets, evidence validation; `investigations/tests/test_lifecycle.py`, `mcp_server/tests/`. **Blocked for live verification:** no provider key; see `HERMES_INTEGRATION.md` spike table. |
| The agent identifies evidence across multiple documents | verified (FakeRunner) | `test_end_to_end_three_documents_with_chunk_level_citations`: decision, alternative and revision cited at chunk level; approval reported `undocumented`; no approval invented |
| The application shows the resulting investigation | verified | status polling, activity summary, statements with evidence, conflicts, open questions, unsupported statements, cancel; `test_views_list_detail_json_and_cancel` |
| Unsupported claims are not presented as facts | verified | invalid citation ids → `unsupported_statements` (investigations), `unsupported` (answers); `test_invented_citation_becomes_unsupported_statement` |
| Unauthorized users cannot retrieve restricted documents | verified | cross-user and cross-organization tests, token tests, membership removal, runtime-role tests |
| Organization isolation is enforced | verified | RLS coverage test, kb_app privilege tests, composite FK rejection tests |
| Tests and deployment instructions are provided | provided | this suite; `README.md`, `docker-compose.prod.yml`, `Caddyfile.example`, `.env.example` |
| Decision records with verification workflow | verified | candidate → draft → verified → superseded, evidence-bound visibility, timeline with `unknown` stages, extraction to candidates; `decisions/tests` |
| Evaluation framework | provided | `eval/` with results file; thresholds hold on the keyword path |

## Not done, blocked, or assumed

- **No live provider or tenant was available.** Everything that needs Google, Microsoft, an LLM key or a Hermes model run is mock-tested and marked above. The attestation gate keeps Deep Investigation closed until a key is configured and the self-check passes.
- The Hermes `tool_use` names for MCP tools are expected to be `mcp_knowledge_<tool>` (documented naming); the attestation accepts `search_knowledge` as well until a live run confirms the exact prefix. The attestation checks the enforcement point behaviorally (an adversarial prompt must produce zero non-knowledge tool calls) because `hermes-agent --list-tools` prints the whole registry regardless of filters.
- Decision extraction after publish exists as a task but is off by default (`DECISION_EXTRACTION_ENABLED`): it calls the answer model for every new revision.
- `find_related_documents` similarity is meaningless with the mock embedder.
- The OpenAI composer uses `chat.completions` with a JSON-schema response format against SDK 3.x; untested live.
- Ranking: the plan's optional reranker protocol is not implemented; retrieval is RRF over the two legs.
- Reconciliation and freshness are time-based (12 h reconcile, 24 h bound). Large tenants may need longer intervals and therefore a larger bound.
- Celery runs with a static beat schedule (ADR 007); no runtime schedule editing.
- No SSO/MFA (ADR 002).
- Runtime-role coverage: the suite runs as the migrator; targeted tests run as `kb_app` through the `runtime_role` fixture.
- `make hermes-build` requires about 3.3 GB of Docker image and a successful apt step; the first attempt in this session failed on Docker disk space and succeeded after a prune.

## Codex inspections

Sprint 1: 17 findings, all fixed (commit c9b55ce). Sprints 2–3: 23 findings, all fixed (commit 1a919b4), including two real races the regression tests exposed (purge erasing the runner record of a still-running investigation; a stale token acting under a newer attempt). Findings and dispositions are in `PLAN-REVIEW-LOG.md`. The reinspection result is appended there.
