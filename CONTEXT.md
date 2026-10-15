# Glossary

One term for one thing. Code and documents use these names.

- **Organization** — the tenant. Every scoped table carries `organization_id`; Postgres RLS enforces `app.org_id`.
- **Membership** — a user's role in an organization: `member`, `steward` (verifies decision records), `admin`.
- **Principal** — the verified identity a request or tool call acts as: user, organization, role, and the investigation when the caller is the agent.
- **Connector link** — a user's delegated OAuth connection to Google Drive or SharePoint. Owned by one user in one organization.
- **Scope** — one change feed of a link: the Google changes feed, or one Graph drive. Grants, sequence numbers and reconcile generations belong to a scope.
- **Document** — one source item with a canonical id (`gdrive:<fileId>`, `sp:<driveId>:<itemId>`), independent of its filename.
- **Version** — one revision of a document, labeled by the provider (`headRevisionId`, Google `version`, Graph `cTag`). Chunks and embeddings belong to a version.
- **Grant** — an `AccessGrant`: this scope's crawl observed this version. Valid when unrevoked, revalidated within the freshness bound, with an active link, user and membership.
- **Revalidation** — an applied item event or a complete scope listing that refreshes a grant's `last_revalidated_at` (observation time, not processing time).
- **Fence** — a revoked grant without a version, written when a removal arrives before any publish, so an older staged publish is obsolete.
- **Chunk** — a passage of a version with heading path, locator (page, slide, sheet, character offsets) and a content hash.
- **Evidence id** — `chunk:<id>@<version label>[start:end]`; the only citable unit.
- **Investigation** — one Deep Investigation: a Hermes run with its own capability token, budgets and evidence log.
- **Capability token** — the per-investigation bearer the MCP server resolves to a principal. Minted in the worker, hashed in the database, revoked on every terminal transition.
- **Candidate / draft / verified / superseded** — the states of a decision record. Only a steward moves a record forward; only verified records are authoritative.
- **Evidence-bound** — visible only to a reader who can see every supporting version.
- **Purge** — removal of a version's content and of every derived text that used it.
