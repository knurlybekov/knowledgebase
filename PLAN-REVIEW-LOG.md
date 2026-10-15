# Plan Review Log: Organizational Intelligence Platform with Hermes Agent
Phases 0-1 (recon + interrogation) complete — plan locked with the user on 2026-10-14. MAX_ROUNDS=5.
Reviewer: codex-cli 0.159.3, model gpt-6-astra (xhigh) from ~/.codex/config.toml. PLAN_FILE=/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md (plan mode; copied to repo PLAN.md at build start).

## Round 1 — Codex

The plan has material security and correctness problems. References below use line numbers from the [plan](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md). No files were modified.

1. **P1 — D1 disables its own security configuration** (lines 30, 79). `--ignore-user-config` discards the generated `HERMES_HOME/config.yaml`, including the MCP configuration and memory settings. The proposed `hermes -z` fallback also loads tools, memory, and working-directory rules normally; it does not preserve the stated restrictions automatically. These behaviors are explicit in the [pinned Hermes CLI source](https://raw.githubusercontent.com/NousResearch/hermes-agent/v0.22.1/hermes_cli/_parser.py).
   **Fix:** Load the isolated trusted configuration and fail startup unless the exact invocation demonstrates the required tools, instructions, memory settings, and limits.

2. **P1 — The copied task transaction breaks investigations** (lines 16, 71, 82). The sibling’s [task base](/Users/karennurlybekov/Desktop/EMPlanPlatform/infra/tasks.py:52) wraps the entire task in `transaction.atomic()`. A streaming investigation using that pattern leaves its `running` transition and heartbeats uncommitted until completion; MCP sees stale state, polling sees no progress, and cancellation can block behind its writes.
   **Fix:** Carry organization identity through the task, but commit state changes in short scoped transactions before and between external calls.

3. **P1 — Capability authentication has an RLS bootstrap deadlock** (lines 53, 61, 80). `CapabilityToken` is organization-scoped, but middleware looks it up before entering `with_org`; without the GUC, RLS hides the token needed to discover the organization.
   **Fix:** Supply an untrusted organization routing hint, enter that scope, then authenticate the token hash and verify its organization, user, and investigation bindings.

4. **P1 — ASGI middleware scope does not establish the tool’s database scope** (line 80). A transaction/GUC opened in middleware cannot be assumed to survive MCP background dispatch or execute on the same connection as a synchronous tool. Django also requires transactional work to run in a synchronous function rather than directly in async code. [Django documentation](https://docs.djangoproject.com/en/6.0/topics/async/)
   **Fix:** Run authorization, `with_org`, ORM access, and result materialization inside one synchronous per-tool operation invoked through the async adapter.

5. **P1 — D3 can leak unpublished SharePoint content between authorized readers** (lines 34, 58). Document access does not imply access to the same version: an editor can see a draft while a reader sees only the published version. Deduplicating both into one global `current_version` and chunk set exposes the editor’s content to the reader. [Microsoft’s versioning documentation](https://support.microsoft.com/en-au/sharepoint/lists/documents-and-library/how-versioning-works-in-lists-and-libraries)
   **Fix:** Bind access grants to authorized content revisions, or explicitly restrict ingestion to a common published revision whose visibility is verified.

6. **P1 — Offboarding and connector revocation do not invalidate authorization** (lines 57, 65, 80). The visibility predicate checks neither active membership nor connector status; MCP checks token validity and investigation status but not current membership. Removing a member or revoking their connector therefore leaves usable grants and potentially running capabilities.
   **Fix:** Check active user/membership and grant-producing link status on every authorization path, and transactionally invalidate grants and capabilities during unlinking or offboarding.

7. **P1 — External revocation has no bounded enforcement time** (lines 34, 149–150). If credentials stop working or access to an entire drive disappears, per-file removal events may never be consumed. Sampling cannot detect every revocation, and “every N syncs” gives no deadline when sync fails. Google actually documents `removed` as including loss of access, but that does not solve failed polling or drive-level removals. [Google change resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes)
   **Fix:** Define a permission-freshness deadline per crawl scope, deny stale grants, handle scope-wide loss, and require request-time provider checks if “exactly currently authorized” remains the promise.

8. **P1 — `DocumentAccess` loses grant provenance** (line 58). It stores one `link` but is unique on `(document, user)`; two linked accounts belonging to the same user cannot independently grant access. Updating or revoking either link can overwrite or incorrectly revoke the other grant.
   **Fix:** Store grants uniquely per document and connector link, deriving user visibility from the existence of any valid grant.

9. **P1 — Document filtering does not authorize saved answers or decision records** (lines 60–65, 87–88). An answer or decision can contain information from several documents. Filtering its citations or finding one visible evidence item does not authorize the remaining prose, rationale, participants, or alternatives. Ownership rules for investigation read/cancel operations are also unspecified.
   **Fix:** Define ownership and complete source-dependency checks for every derived object, denying the whole object after access loss unless it is safely regenerated.

10. **P1 — Purge contradicts both the schema and copied audit implementation** (lines 19, 58–63, 91). Purging chunks leaves `DocumentVersion.content_text`, structures, reference excerpts, decision evidence, and generated paraphrases. Worse, the copied [audit trigger](/Users/karennurlybekov/Desktop/EMPlanPlatform/infra/migrations/0001_initial.py:33) records entire old/new rows—including deleted content—and the [immutability migration](/Users/karennurlybekov/Desktop/EMPlanPlatform/infra/migrations/0003_audit_log_immutable.py:9) prevents removing them. Chunk-backed evidence also needs explicit deletion behavior.
    **Fix:** Specify a complete purge dependency graph and FK behavior, audit only allowlisted metadata, and invalidate derived text rather than attempting excerpt-only redaction.

11. **P1 — Last-access purge races with grants and ingestion** (lines 34, 72). A purge can observe zero grants, then delete chunks after another crawl grants access; conversely, an already-running ingestion can recreate content after the last grant was revoked. Regranting unchanged content can also hit the hash-skip path despite having no remaining chunks.
    **Fix:** Serialize grant/purge/publication decisions per document and use generation checks so stale jobs cannot publish and purged documents must rebuild.

12. **P1 — The two authorization layers are not independently specified** (lines 53–65). `visible_documents` relies on the RLS organization scope instead of explicitly matching `principal.organization`. Separately, organization IDs on children do not enforce matching parents: a chunk can claim organization A while referencing a document or version from B. PostgreSQL foreign-key checks bypass RLS. [PostgreSQL documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
    **Fix:** Add explicit organization predicates and database-enforced consistency for organization, document/version, link/user, evidence, and capability relationships.

13. **P1 — The copied runtime role can dismantle the database protections** (lines 16, 70). The [initialization script](/Users/karennurlybekov/Desktop/EMPlanPlatform/scripts/postgres-init/01-extensions-and-app-role.sh:39) grants schema creation and database creation, with the application role used to own migrated tables. `NOBYPASSRLS` does not prevent an owner from disabling RLS; the row-level audit guard also does not cover `TRUNCATE`. [PostgreSQL documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
    **Fix:** Separate migration/test ownership from runtime roles and deny runtime DDL, `TRUNCATE`, and unnecessary table access.

14. **P1 — MCP request accounting is not tool-call authorization** (lines 38, 80). Middleware counts transport requests, which also include initialization and discovery. An atomic increment alone does not atomically enforce the maximum. Session reuse, expiry after initialization, concurrent calls, and the cumulative 60,000-character limit are unspecified. MCP sessions span multiple requests. [MCP transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
    **Fix:** Prefer stateless transport and authorize each tool execution with conditional budget reservations, cumulative output accounting, and investigation-wide limits that survive retries.

15. **P1 — “Seen document” is too coarse to validate evidence** (lines 61, 80, 82, 88). Seeing one search excerpt currently authorizes citations or candidate evidence from the entire document, including unseen chunks or later versions. Concurrent JSON appends can lose seen IDs. Dropping an invalid citation also leaves its unsupported claim intact.
    **Fix:** Record uniquely identified evidence actually returned—revision, chunk, and span—recheck access when consuming it, and reject or regenerate claims with invalid evidence.

16. **P1 — Runner creation and investigation completion lack an idempotent lifecycle** (lines 81–82). A successful `POST /runs` followed by a lost response can create a second process on retry. Worker redelivery can do the same. Late completion can overwrite cancellation, and issuing fresh tokens on retry can reset budgets or extend the deadline.
    **Fix:** Use a stable investigation/attempt key, idempotent runner creation, conditional state transitions, one overall deadline/budget, and token revocation on every terminal transition.

17. **P2 — A separate home directory is not a complete isolation or cleanup boundary** (lines 30, 81, 132). Processes still share the container’s filesystem and identity unless otherwise constrained. Exit cleanup does not run after runner crashes, and signalling one PID does not establish that descendants terminate.
    **Fix:** Specify the trusted-runtime boundary, isolate run directories and environments, supervise process groups, and reconcile orphan processes and directories at startup.

18. **P1 — The Google connector never bootstraps existing documents** (line 74). `getStartPageToken` followed by `changes.list` starts tracking future changes; unchanged documents that predate linking are never ingested. [Google change API](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes)
    **Fix:** Capture the start token, perform a complete paginated initial listing, then replay changes from that token.

19. **P1 — SharePoint discovery depends on an endpoint about to stop working** (line 74). Microsoft says `sharedWithMe` is degraded and stops returning data in November 2026, immediately after this plan’s date. Own-drive and followed-drive discovery also do not establish coverage of every accessible SharePoint library. [Microsoft documentation](https://learn.microsoft.com/en-us/graph/api/drive-sharedwithme?view=graph-rest-1.0)
    **Fix:** Replace that dependency with supported discovery or explicit user-selected sites/libraries, and state the resulting coverage boundary.

20. **P1 — The document uniqueness key is underspecified for Graph** (lines 34, 58). Graph item IDs are unique within a drive, not across all drives; storing `drive_id` separately does not include it in deduplication. Shared-item wrappers also need normalization to the underlying item. [Graph resource definition](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0)
    **Fix:** Define a canonical source identity containing the provider namespace, drive ID, and underlying item ID before applying uniqueness or access updates.

21. **P1 — Cursor advancement is not tied to durable ingestion** (lines 57, 72, 74). Advancing a cursor after enqueueing work loses changes if the enqueue or worker fails; advancing only after processing still requires safe replay. Overlapping syncs can overwrite cursors, while an incomplete full rescan can mistakenly revoke unseen grants.
    **Fix:** Serialize syncs per link/scope, atomically persist changes with checkpoints, and sweep missing grants only after a successfully completed reconciliation generation.

22. **P1 — Hash comparison does not provide ingestion idempotency or ordering** (lines 58–59, 72). Two users can ingest the same document concurrently, producing duplicate versions/chunks; an older slow job can publish after a newer one. The plan defines no version/chunk uniqueness or guarded publication. Graph explicitly permits repeated items within a delta feed. [Graph delta documentation](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0)
    **Fix:** Define revision and transformation identities, enforce unique version/chunk keys, stage processing outside transactions, and conditionally publish only the current generation.

23. **P1 — The tests do not establish the stated acceptance criteria** (lines 90, 136–144). Test 11 exercises a fake runner, not Hermes; test 16 proves that the fake ignores injections. Tests 3–6 omit concurrent ingestion, account/drive loss, regranting, and purge races. Test 9 checks citation membership, not support for claims. Test 15’s copied coverage checks do not prove every policy’s behavior. Steward authorization and derived-object revocation are missing, and retrieval metrics have no pass thresholds.
    **Fix:** Add a criterion-to-test matrix with real Hermes contract tests, adversarial authorization/concurrency tests, decision-workflow tests, grounding checks, and explicit metric thresholds; keep unverified live criteria blocked.

24. **P2 — Observability cannot demonstrate that revocation and recovery work** (lines 57, 63, 81–82, 91). `last_sync_at`, error codes, and tool durations cannot reveal stale permission scopes, incomplete purges, duplicate attempts, orphan processes, or rejected access. A healthy runner endpoint does not prove safe investigation execution.
    **Fix:** Define correlated identifiers and metrics for permission freshness, denied access, checkpoint progress, purge completion, runner attempts/orphans, and investigation resource usage.

VERDICT: REVISE
### Claude's response (revision 2)
Accepted and incorporated (24 of 24, with scope notes):
1. Dropped `--ignore-user-config` (verified in `_parser.py` v0.22.1: it ignores config.yaml). Isolation via per-run HERMES_HOME. Added runner configuration attestation (self-check MCP, tool set assertion) before runs; `--safe-mode` rejected because it disables MCP.
2. New D5: OrgAwareTask sets context only; every write in a short `with_org` transaction; external calls outside transactions.
3. CapabilityToken is a global (no-RLS) auth table looked up by hash, then `with_org(token.organization_id)` and binding checks.
4. Per-tool authorization + ORM + serialization in one sync unit via sync_to_async; stateless streamable HTTP.
5. Grants bind to revisions: `AccessGrant(document, link, version)`; chunk sets per version; draft vs published never shared.
6. `valid_grants` checks membership status, user active, link status; offboarding/unlink revokes grants, tokens and running investigations in one transaction; MCP rechecks per call.
7. `PERMISSION_FRESHNESS_MAX_AGE` (24 h default) denies stale grants; link error invalidates all grants; scope-wide loss handled; `removed` semantics verified in Google docs (covers loss of access).
8. Grant unique per (document, link); user visibility derived from any valid grant.
9. Owner-only derived objects (admins metadata only); whole-object `evidence_revoked` on any failed recheck; DecisionRecord `evidence_bound` default with audited steward `organization` visibility.
10. Full purge dependency graph; audit trigger logs allowlisted metadata columns only.
11. Per-document advisory lock around grant/purge/publish; `Document.generation`; hash-skip requires present chunks.
12. Explicit `organization_id = principal.organization_id` predicate; composite FKs `(organization_id, parent_id)` via RunSQL on all child relations.
13. Two roles: `kb_migrator` (owner, migrations, tests) and `kb_app` (runtime, no DDL, no TRUNCATE); test asserts denial.
14. Stateless transport; conditional-update budget reservation for tool calls and cumulative output chars; discovery free; limits on the Investigation row survive retries.
15. `InvestigationEvidence` at chunk+span level replaces seen_document_ids JSON; citations validated against it and rechecked; unsupported statements moved to a separate section, never presented as findings.
16. Idempotent lifecycle: run_key = id:attempt, runner idempotent on run_key, conditional transitions, single deadline, same token/budget on retry, token revoked on every terminal transition.
17. Process groups, 0700 run dirs, orphan reconciliation from an on-disk registry, trusted-runtime boundary stated (shared container) as a known limitation.
18. Google bootstrap: start token, full files.list (user corpus + each shared drive), then replay.
19. `sharedWithMe` removed; explicit site/library selection + own drive; coverage boundary shown in UI.
20. Canonical ids `sp:<driveId>:<itemId>` (remoteItem for wrappers), `gdrive:<fileId>`.
21. Per-link advisory lock; ChangeInbox rows + cursor in one transaction per page; sweep only after a completed reconcile generation.
22. Unique (document, version_label), unique (version, position); staged processing, locked conditional publish by generation.
23. Criterion-to-test matrix added, including live `hermes`-marker contract tests, concurrency tests, decision workflow tests, metric thresholds (with the MockEmbedder caveat stated honestly).
24. Observability: correlation ids and named metrics for grant freshness, denials, checkpoints, purges, runner attempts/orphans, investigation usage.
Rejected: none. Partially scoped: the "request-time provider check" in item 7 is not adopted (it would add a provider round trip per query and per-user tokens would be needed on the MCP path); the bounded freshness deadline is the chosen promise and is documented as such.

## Round 2 — Codex

Revision 2 still has material problems, including several introduced by the fixes. I reviewed the [revised plan](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md) without modifying files. “Addressed” below means addressed in the design, not verified in running code.

| Prior finding | Status | Revision 2 assessment |
|---|---|---|
| 1. Hermes ignores generated configuration | Addressed | Flag removed; configuration attestation required. |
| 2. Whole-task transaction | Addressed | D5 explicitly replaces it with short transactions. |
| 3. RLS bootstrap during capability authentication | **Open** | Token lookup is now possible, but investigation reads and updates still precede `with_org`. |
| 4. Async/ORM connection scope | Addressed | A synchronous per-tool database unit is specified. |
| 5. Different users see different revisions | **Partial** | Version grants exist, but downloaded bytes are not bound safely to their revision label. |
| 6. Offboarding and connector revocation | Addressed | Active-user/membership/link predicates and invalidation handlers are explicit. |
| 7. Unbounded external revocation | **Partial** | A 24-hour limit exists; renewal, expiration cleanup, and the “exactly authorized” promise remain inconsistent. |
| 8. Grant provenance | Addressed | Grants are now unique per document/link. |
| 9. Authorization of derived objects | **Partial** | Only cited dependencies are checked; organization-visible decisions introduce a bypass. |
| 10. Incomplete purge and immutable content audit | **Partial** | Audit allowlisting fixes content duplication; purge still conflicts with FKs and omits stored text. |
| 11. Purge versus ingestion races | **Open** | Revocation/purge do not advance the generation checked by staged publication. |
| 12. Independent filters and relational consistency | **Partial** | Organization filtering is explicit; same-organization relationship mismatches remain possible. |
| 13. Runtime role can disable protections | Addressed | Roles are separated and runtime DDL/TRUNCATE denial is tested; the new privileged trigger needs hardening. |
| 14. MCP authorization and budgets | **Partial** | Per-tool accounting exists, but cancellation and cumulative-output races remain. |
| 15. Evidence provenance and claim validation | **Partial** | Returned spans are recorded; valid citation identifiers still do not establish support for claims. |
| 16. Idempotent investigation lifecycle | **Partial** | Stable run keys help; secret delivery, dispatch recovery, replay, and attempt fencing remain incomplete. |
| 17. Isolation and cleanup boundary | Addressed | Shared-container trust is acknowledged; process-group cleanup is specified, with a new PID-reuse problem. |
| 18. Google initial ingestion | Addressed | Initial listing followed by change replay is explicit. |
| 19. Deprecated SharePoint discovery | Addressed | Replaced with explicit library selection and a stated coverage boundary. |
| 20. Graph document identity | Addressed | Canonical identity includes drive and underlying item IDs. |
| 21. Durable cursor advancement | **Partial** | Durable inbox exists; synchronization and reconciliation completion are still unsound. |
| 22. Ingestion ordering/idempotency | **Partial** | Uniqueness and staging help, but generation checks do not prevent stale grant restoration. |
| 23. Acceptance-test coverage | **Partial** | Matrix, live contracts, and thresholds improve coverage; significant negative cases remain absent. |
| 24. Observability | Addressed | Correlation identifiers and operational metrics are now specified. |

The remaining and newly introduced problems are:

1. **P1 — MCP still accesses protected rows before establishing scope** — line 113. Making `CapabilityToken` global solves only its lookup. Checking `investigation.status`/`deadline_at` and updating its budget before `with_org` still encounters investigation RLS without an organization GUC. Valid calls fail.
   **Fix:** Perform only the token lookup globally, then enter `with_org` before loading or modifying any investigation or organization-scoped row.

2. **P1 — The raw capability token never reaches the worker** — lines 72, 105–106. `start_investigation` mints the secret, stores only its hash, and queues `run_investigation(id)`; the worker cannot reconstruct the bearer needed for `POST /runs`. Retrying with “the same token” has the same unresolved delivery requirement.
   **Fix:** Mint and commit the token in the claimed worker immediately before launch, retaining the raw value in memory for its retry and defining rotation for recovery.

3. **P1 — The sync lock contradicts D5 and its advertised behavior** — lines 39, 86. `pg_advisory_xact_lock` waits rather than returning immediately, and releases when its transaction commits. It cannot serialize a sync spanning external calls and multiple short transactions. [PostgreSQL lock documentation](https://www.postgresql.org/docs/17/explicit-locking.html), [lock functions](https://www.postgresql.org/docs/17/functions-admin.html)
   **Fix:** Use a nonblocking session lock on a dedicated connection with guaranteed release, or a durable lease with a fencing token and stable lock identity.

4. **P1 — Staged ingestion can restore revoked access** — lines 89–90. Publication increments `Document.generation`; removal and purge do not. An ingest staged at generation 5 can therefore publish after a removal at generation 5 and restore the grant. The existing-content fast path also lacks the publication guard. Rebuilding a tombstone never explicitly restores `Document.status = active`.
   **Fix:** Fence every grant/content mutation—including fast-path refresh, revocation, and purge—and reject obsolete source events before atomically publishing and updating document status.

5. **P1 — A revision label does not bind the downloaded content** — lines 69, 89, 123. Metadata can identify revision A, then an unpinned download/export can return revision B after an edit. Those bytes become shared under A’s grants. Google’s native files also lack the proposed `headRevisionId`; `modifiedTime` is writable, while Google provides a monotonic `version` field. [Google file fields](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
   **Fix:** Pin downloads to provider revisions where supported, otherwise validate the revision before and after downloading and retry on change; use a provider-defined stable revision discriminator.

6. **P1 — Freshness expires unchanged documents despite successful syncing** — lines 35, 89–91. Empty incremental feeds never refresh individual grants, so unchanged documents expire after 24 hours unless a full reconciliation happens sufficiently often. “Every N syncs” establishes no wall-clock guarantee. Expiration and moving a grant to another version also have no specified purge trigger.
   **Fix:** Define a wall-clock renewal protocol and expiration sweeper, preserve provider observation timestamps across replay, and align the goal with the explicitly accepted staleness window.

7. **P1 — Full reconciliation has no reliable generation barrier** — lines 68–69, 88, 91. Grants have no `last_seen_generation`, and inbox rows have no explicit reconciliation generation. A timestamp cannot establish which completed scan observed a grant. Finishing pagination while its inbox remains unprocessed can wrongly revoke grants for documents already discovered.
   **Fix:** Stamp inbox rows and grants with reconciliation generations, and permit sweeping only after the complete scan and its required inbox work have been applied.

8. **P1 — The purge sequence cannot preserve its evidence rows as written** — lines 62, 71–73, 96. Chunks are deleted before `DecisionEvidence` is handled, despite its surviving FK references. Afterwards, chunk-only answer references may no longer identify the affected version. `Answer.claims_json` retains claim text after `answer_text` is redacted, and decision prose is omitted entirely. Investigation invalidation also lacks a separate declared content-status field.
   **Fix:** Capture and invalidate dependencies before deletion, retain durable evidence tombstones with explicit nullable-FK behavior, and purge every text-bearing field using a content state separate from execution status.

9. **P1 — Citation-only authorization still leaks derived information** — lines 81, 101, 106. A model can use secret source A while citing public source B; revoking A then leaves the answer readable. Moving text with revoked evidence into `unsupported_statements` is also disclosure if that warning section remains visible.
   **Fix:** Authorize derived objects against all evidence supplied to generation, and withhold every output section when any required dependency loses authorization.

10. **P1 — Organization-visible decisions introduce an undefined declassification mechanism** — lines 73, 81, 96. A steward can make source-derived text readable without source access. The plan does not require the publishing steward to access all evidence, and later source revocation/purge does not remove the organization-visible description or rationale.
    **Fix:** Remove this visibility mode from the initial release, or explicitly define publication authority, required source access, and post-publication revocation and retention semantics.

11. **P1 — Composite organization FKs still allow contradictory relationships** — line 62. A chunk can reference document A and a version belonging to document B when both are in the same organization; grants and evidence have analogous inconsistencies. Token organization consistency likewise does not establish that its user owns the referenced investigation.
    **Fix:** Derive redundant relationships where possible; otherwise enforce document/version, chunk/version, and token/investigation-user consistency with matching composite constraints.

12. **P1 — The new membership RLS exception has no usable execution model** — lines 39, 60, 79. Membership has a “user-scoped policy,” but `with_org` sets only `app.org_id`. No actor propagation or administrative/worker policy is specified. Offboarding other users and counting all remaining valid grants cannot safely depend on visibility of only the caller’s membership.
    **Fix:** Specify actor propagation and service/admin policies, or retain organization-scoped membership access with a narrowly defined self-membership lookup before organization selection.

13. **P1 — Budget reservation can succeed after cancellation and exceed the output cap** — line 113. The update checks only the counter, so cancellation can occur after the preceding authorization check and still be followed by an accepted call. For output, `used < max` does not ensure `used + response_length <= max`; concurrent calls can calculate the same remaining allowance.
    **Fix:** Reserve budgets inside the scoped authorization transaction with current state/deadline checks, atomically allocate remaining output capacity, and record only spans actually returned.

14. **P1 — Runner idempotency does not cover dispatch, restart, or replay** — lines 105–107, 119. Database creation followed by enqueueing is not a durable dispatch protocol. The registry stores only `pgid` and directory, not durable terminal outcomes. Reconnection replays all events without event IDs, and completion checks only `status='running'`, not the current attempt/run key.
    **Fix:** Add durable dispatch, persisted terminal run records, sequenced replay with a consumer cursor, and state transitions conditional on the current attempt/run key.

15. **P1 — The new `SECURITY DEFINER` audit trigger needs an explicit safety boundary** — line 59. The copied trigger uses an unqualified audit-table name. Promoting it to migrator privileges without a fixed safe `search_path` permits temporary-table shadowing; denying schema `CREATE` does not address that. PostgreSQL explicitly documents this hazard. [Security-definer guidance](https://www.postgresql.org/docs/17/sql-createfunction.html)
    **Fix:** Schema-qualify referenced objects, fix a trusted `search_path` with `pg_temp` last, restrict function privileges, and test temporary-object shadowing as `kb_app`.

16. **P2 — Orphan reconciliation can kill an unrelated process** — lines 31, 119. A persisted numeric PGID is not a durable process identity; after restart or PID reuse, it may identify a different process group.
    **Fix:** Verify process start identity and container/boot identity before signalling, or use a supervisor-owned handle that cannot target a reused process group.

17. **P1 — The revised tests still miss the failures that determine acceptance** — lines 194–217. Add explicit cases for revoke-during-download, empty-delta freshness, unfinished reconciliation processing, same-org FK mismatches, surviving evidence after purge, `claims_json` erasure, cancelled concurrent tool calls, raw-token delivery, and replay across runner restart. Grounding still tests identifier validity rather than whether evidence supports the claim.
    **Fix:** Add these negative tests and claim-support evaluations to the acceptance matrix, running authorization paths as `kb_app` and treating skipped live criteria as unverified.

VERDICT: REVISE
### Claude's response (revision 3)
Accepted and incorporated (17 of 17):
1. MCP unit order fixed: global token lookup only, then `with_org`, then investigation reads and budget updates.
2. Token is minted in the worker after the `queued → dispatched` claim; raw value stays in task memory; retry and crash recovery rotate the token; budgets and deadline live on the Investigation row.
3. Scope sync uses a durable `SyncLease` with a fencing token on every write; advisory locks are restricted to single short transactions (publish/revoke/purge of one document). D5 updated.
4. Every grant or content mutation (publish, fast-path refresh, revoke, purge, tombstone, reactivate) increments `Document.generation` under the document lock; inbox events are fenced by `AccessGrant.last_event_seq`; tombstone rebuild restores `active`.
5. Downloads pinned or validated: Google binary via `revisions.get(headRevisionId)`, Google native via export with `version` before/after check, Graph via `/content` with `cTag` before/after check (verified: Graph serves pinned content only for previous versions). Version labels: `headRevisionId` / monotonic `version` / `cTag`.
6. Renewal protocol: a successful scope sync renews all grants in the scope (`scope.last_ok_at`), because both feeds report loss of access; explicit promise "as of last successful sync, bounded by 24 h"; expiration sweeper added; grant moves trigger `maybe_purge`.
7. `reconcile_generation` stamped on inbox rows and grants; sweep only after the scan completed and no inbox row of that generation is pending; wall-clock reconcile interval.
8. Purge order rewritten: dependents invalidated before chunk deletion; `DecisionEvidence.chunk` nullable with durable tombstone columns; all text-bearing fields purged including `claims_json`, decision prose; `content_state` separated from execution `status` on Answer, Investigation, DecisionRecord.
9. D6: derived objects authorized against all supplied evidence; whole object withheld on any failure, including the unsupported-statements section.
10. Organization-wide decision visibility removed from this release.
11. Composite constraints for document/version, version/chunk, link/membership, token/investigation-user consistency, with tests.
12. Membership stays organization-scoped; hardened `SECURITY DEFINER` `my_memberships(user_id)` for the pre-organization picker; `app.actor_id` set with `app.org_id`.
13. Budget reservation inside the scoped transaction with `status='running' AND deadline_at > now() AND run_key = :run_key`; output capacity allocated atomically with LEAST; evidence recorded only for returned spans.
14. Dispatch recovery via reaper on stale `queued`/`dispatched`; runner persists terminal records until `DELETE` ack; sequenced events with `?after=seq` replay surviving runner restart; transitions conditional on `run_key`.
15. Audit trigger hardened: schema-qualified, `search_path = pg_catalog, infra, pg_temp`, EXECUTE revoked from PUBLIC, shadowing test as `kb_app`.
16. Orphan reconciliation checks pgid + process start time + boot id before signalling.
17. Matrix extended with the named negative cases; authorization tests run as `kb_app`; claim-support check (substring proxy in CI, LLM judge behind a flag) labeled honestly.
Rejected: none.

## Round 3 — Codex

Revision 3 is substantially closer, but **three material design problems remain**. The other issues below can be resolved during implementation. No files were modified.

Using the round-2 numbering:

| # | Prior finding | Revision 3 assessment |
|---|---|---|
| 1 | MCP touches protected rows before setting organization scope | **Addressed:** authorization ordering is explicit. |
| 2 | Worker cannot obtain the raw capability token | **Addressed:** worker mints it and sends it directly to the runner. |
| 3 | Transaction advisory lock cannot span the crawl | **Addressed:** durable leases with fencing replace it. |
| 4 | Ingestion can resurrect revoked grants or mishandle tombstones | **Addressed:** mutations increment generation; publication checks it; reactivation is explicit. |
| 5 | Revision labels are not bound to downloaded bytes | **Partial:** native Drive and Graph checks improve this; the new Google binary path introduces blocker B below. |
| 6 | Permission freshness, renewal and expiration are incomplete | **Partial:** expiration is specified, but blanket renewal introduces blocker A. |
| 7 | Reconciliation lacks a generation and processing barrier | **Addressed at design level:** generation and barrier exist; tighten failure handling during implementation. |
| 8 | Purge has incomplete dependencies, fields and FK ordering | **Addressed for database content:** ordered purge and separate content state are specified. |
| 9 | Citation-only authorization leaks uncited input | **Addressed:** D6 tracks all supplied evidence. |
| 10 | Organization-wide decisions bypass evidence permissions | **Addressed:** that publication mode is removed. |
| 11 | Same-organization relationships can still be inconsistent | **Addressed:** document/version/chunk and token-owner constraints are explicit. |
| 12 | Membership discovery conflicts with RLS and actor semantics | **Partial:** the replacement function still conflicts with forced RLS; blocker C. |
| 13 | Concurrent calls overspend budgets or bypass cancellation | **Addressed:** transactional reservations and output allocation are specified. |
| 14 | Dispatch, recovery and replay lack durable state | **Addressed at architecture level:** persisted events, terminal records and attempt fencing are present. |
| 15 | Audit `SECURITY DEFINER` function is insufficiently hardened | **Addressed:** ownership, search path, qualification and shadowing tests are specified. |
| 16 | Reused PGIDs can cause unrelated processes to be killed | **Addressed:** process identity is checked before signaling. |
| 17 | Tests miss acceptance criteria and overstate grounding | **Addressed in the proposed matrix:** negative cases are expanded, grounding proxies are labeled, and skipped live checks remain unverified. |

The remaining blockers are:

1. **A — Successful polling does not establish the promised permission freshness.**  
   [D3, line 35](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md:35) renews *every* grant after any successful delta, including an empty response. The claim that Graph’s `deleted` facet covers all access loss is not established by the documented contract. Microsoft describes permission-hierarchy processing separately, including sharing changes on ancestors; ordinary delta results do not necessarily enumerate every affected descendant. A folder or group permission change can therefore leave the drive accessible while the plan lacks a reliable way to invalidate affected grants. Successful polling keeps renewing them, defeating the 24-hour bound; reconciliation defaults to seven days. See [Microsoft’s scanning guidance](https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/scan-guidance?view=odsp-graph-online) and [delta permission requirements](https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0#scanning-permissions-hierarchies).  
   **Fix:** Base authorization expiry on successful per-item or complete-scope access revalidation within the freshness bound, separately from polling health, and advance it only after relevant revocations are applied.

2. **B — The new Google binary download strategy is incompatible with ordinary reader access.**  
   [Upsert path, line 98](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md:98) requires `revisions.get(headRevisionId, alt=media)`. Google documents revision-history access for writer-level roles and above, and says downloadable blob revisions must be marked `keepForever`. A delegated account that can read a PDF does not necessarily satisfy either condition; `drive.readonly` cannot mark revisions for retention. This breaks normal ingestion, not merely an unusual retry case. See [Google’s revision restrictions](https://developers.google.com/workspace/drive/api/guides/manage-revisions).  
   **Fix:** Use [`files.get(alt=media)`](https://developers.google.com/workspace/drive/api/guides/manage-downloads) for current binary content, with before/after revision validation and checksum verification where available.

3. **C — `SECURITY DEFINER` alone does not make membership discovery work under forced RLS.**  
   [Database policy, line 63](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md:63) retains organization-only RLS on `Membership`, then calls `my_memberships(user_id)` before an organization is selected. Under the stated roles, the function owner remains subject to `FORCE ROW LEVEL SECURITY`; with no organization GUC, it sees no memberships. PostgreSQL explicitly documents that [forced RLS applies to table owners](https://www.postgresql.org/docs/17/ddl-rowsecurity.html). Calling the function “hardened” does not supply the missing policy.  
   **Fix:** Specify a narrow, SELECT-only pre-organization membership path bound to the authenticated actor, and test it with `app.org_id` unset.

These are implementation notes, not additional approval blockers:

- **Scope association:** Make each grant’s `SyncScope` unambiguous; freshness, reconciliation generation and event-sequence comparisons must use that same scope.
- **Reconciliation failures:** “No pending rows” still allows `failed` rows; require successful application or safe supersession before interpreting absence as revocation.
- **Investigation transitions:** Coordinate runner startup with the `running` state, reset recovered work to a claimable state, and condition transitions on both the expected status and attempt.
- **Purge during generation:** Recheck content state when saving generated results so an in-flight completion cannot restore purged prose; include durable runner events and terminal text in retention handling.
- **MCP truncation:** Allocate output by trimming evidence fields while preserving valid response structure, then record exactly the spans delivered.

Add regression cases for the three blockers: pre-organization membership lookup, a read-only Google binary file without retained revisions, and inherited permission loss while delta polling continues successfully. The current “empty delta renews” test otherwise validates the unsafe assumption itself.

VERDICT: REVISE
### Claude's response (revision 4)
Accepted all three blockers and all five notes:
A. Grants are revalidated only by applied item events or by a complete scope revalidation (`full_reconcile`, metadata-only full re-enumeration) every `FULL_RECONCILE_INTERVAL` (12 h, enforced ≤ half of the 24 h bound). Incremental polling health no longer renews anything. Promise reworded to "as of the last complete access revalidation". Tests: empty delta does not renew; inherited permission loss detected by reconcile; failed inbox rows block the sweep.
B. Google binary download via `files.get(alt=media)` with `version` before/after check and `md5Checksum` verification; `revisions.get` dropped. Test added for a read-only binary file.
C. `membership_self` SELECT policy bound to `app.actor_id`; the `SECURITY DEFINER` lookup function is removed; test as `kb_app` with `app.org_id` unset.
Notes: grants carry their `scope`; sweep barrier also blocks on `failed` rows; transitions conditional on status and attempt, runner acknowledges start before `running`, recovery resets to `queued` with `attempt + 1`; completion requires `content_state = present`, runner records erased on purge via `DELETE /runs/{run_key}`; MCP truncation trims excerpts while keeping JSON valid and records only delivered spans.
Rejected: none.

## Round 4 — Codex

**Revision 4 is sound enough to implement.** Blockers A–C are addressed. A few implementation details remain, but I found no new architectural blocker. No files were modified.

| Round-3 item | Assessment |
|---|---|
| **A — Permission freshness** | **Addressed.** Per-grant revalidation replaces blanket renewal; full reconciliation runs every 12 hours; empty deltas cannot extend access. Tests cover inherited permission loss. |
| **B — Google reader-compatible downloads** | **Addressed.** `files.get(alt=media)` replaces revision downloads, with version and checksum validation plus a read-only-file regression test. |
| **C — Pre-organization membership lookup** | **Addressed.** The SELECT-only self-membership policy works without organization context; runtime-role tests cover isolation and denied writes. |
| **Note 1 — Scope association** | **Addressed.** Grants explicitly reference their scope, which governs sequence and reconciliation comparisons. |
| **Note 2 — Failed reconciliation rows** | **Addressed.** Failed rows block sweeping until successfully retried or superseded; the matrix includes this case. |
| **Note 3 — Investigation transitions** | **Mostly addressed.** Status/attempt guards and recovery to `queued` are explicit; the startup race below remains. |
| **Note 4 — Purge during generation** | **Mostly addressed.** Completion checks content state, runner retention is included, and a regression test is specified; finalization details remain below. |
| **Note 5 — MCP truncation** | **Addressed.** Trimming preserves JSON structure and records only delivered evidence; test the minimum-capacity boundary. |

Remaining implementation notes:

1. **The first MCP call can still precede `running`.** At [line 123](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md:123), Hermes starts before the runner acknowledges startup and the worker commits `running`; MCP rejects calls while still `dispatched`.  
   **Fix:** Gate the first tool call on committed readiness, and test a call arriving before the startup acknowledgment.

2. **Purged completion needs a separate terminal path.** The completion update requires `content_state='present'`, so it cannot itself produce the promised `completed/purged` state; without another branch, the investigation stays running.  
   **Fix:** Add a conditional terminal transition that preserves `purged`, writes no text, and revokes the token; apply publication-time evidence checks to answers and decisions too.

3. **Purging an active runner needs cancellation before erasure.** [Line 113](/Users/karennurlybekov/.claude/plans/project-enterprise-organizational-indexed-newt.md:113) calls `DELETE`, but the runner contract describes deleting terminal records; an active process could continue writing events.  
   **Fix:** Stop the affected attempt before erasing its records, and test purge while events are being appended.

4. **Freshness timestamps should reflect observation time.** A delayed inbox item must not turn an old access observation into a fresh 24-hour authorization window merely because it was processed now.  
   **Fix:** Persist the successful access-check timestamp and use it for `last_revalidated_at`; add a delayed-processing test.

5. **Valid JSON still needs a minimum output allocation.** Trimming cannot fit even an empty response envelope into zero remaining characters.  
   **Fix:** Define the budget-exhausted response path and test zero capacity and capacity smaller than the minimum payload.

The test matrix now covers the three former blockers and the failed-row reconciliation case. Add these boundary tests during implementation; live connector behavior and Hermes attestation appropriately remain unverified until executed.

VERDICT: APPROVED
### Claude's response (revision 5)
VERDICT: APPROVED after 4 rounds. The five implementation notes are folded into the plan:
1. Readiness gate: runner `POST /runs` persists without starting; worker commits `running`, then `POST /runs/{run_key}/start`; MCP returns retryable `not_ready` for a call before `running`.
2. Separate conditional terminal transition for `content_state = purged`; publication-time evidence recheck for answers and decision records too.
3. Purge cancels active attempts and waits for the terminal record before `DELETE`; runner refuses `DELETE` on an active run.
4. `last_revalidated_at` = provider observation time (`ChangeInbox.observed_at`), not processing time.
5. `MCP_MIN_RESPONSE_CHARS` minimum envelope; below it, an uncharged `budget_exhausted` payload.
Rounds used: 4 of 5. Loop closed. Phase 3 (build) awaits the user's choice of builder.
