# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
First user: the owner, a computing science graduate, over four years of course material (lecture notes, slide decks, PDFs, project reports) spread across Google Drive folders, asking questions mid-study and keeping settled conclusions. The same system serves members of a small team (5 to 50 people) whose working documents live in Google Drive or SharePoint. They ask a question in the middle of a task: a policy figure, where a checklist lives, why a decision was made, what was tried before. A steward (an experienced member) reviews candidate decision records and verifies them. An administrator links accounts and watches sync health. Confirmed by the owner on 2026-10-17; no other audience is confirmed.

## Product Purpose
Knowledgebase connects each member's own drive accounts, indexes what that member is allowed to see, and answers questions with citations back to the files. Quick Search answers a factual question in seconds. Deep Investigation runs a multi-step agent over several documents and reports what is documented, what conflicts, and what is not established. Decision records capture documented decisions with their alternatives and rationale, verified by a steward, so the context does not leave with the people. Success: a member gets a cited answer without asking around, and a newcomer finds the decision, the alternatives, and the reason in one place.

## Positioning
Every answer is bound to evidence the asking member may open. Permissions are not a filter on results: the index itself is per-member, revalidated on a fixed schedule, and an answer, investigation, or decision record is withheld or purged when any evidence behind it becomes invisible. The agent sees only two read-only tools and one short-lived token per run. A neighboring product that indexes a shared drive once and filters at query time cannot truthfully claim this.

## Operating Context
- Documents: Google Docs, Sheets, Slides, Word, Excel, PowerPoint, PDF, text, Markdown. Audio, video, archives, and binaries are recorded as metadata only.
- Sources: Google Drive (verified live 2026-10-16 on a drive of about 3,000 items), SharePoint and OneDrive through Microsoft Graph (mock-tested; live link pending).
- Rhythm: each account is polled every 15 minutes and fully re-listed every 12 hours. A first sync of a large drive takes an hour; the UI shows progress.
- Roles: member, steward, admin. Stewards see pending candidate records. Admins see the Administration page: links, scopes with age, inbox backlog, failures.
- Deep Investigation takes about one minute and polls for status; it can be cancelled.
- Deployment: Docker Compose; development on a laptop at localhost:8010.

## Capabilities and Constraints
- Server-rendered Django templates with HTMX for polling and partial updates. Tailwind CSS v4 through django-tailwind-cli. No JavaScript framework; small vanilla scripts are acceptable.
- Pages: login and password reset; home dashboard; search with mode toggle (Quick Search, Deep Investigation) and answer detail; investigations list and detail with live status, activity, statements, citations, conflicts, open questions, unsupported statements, cancel; decisions list and detail with timeline and steward transitions; connectors page (link, select libraries, sync now, unlink); administration.
- Terminology: organization, member, steward, link (a connected account), scope (one drive or library), grant, revision, chunk, evidence, investigation, capability token, candidate / draft / verified / superseded record.
- Constraint: an answer shows statements only when their citations were returned to that run; unsupported statements render separately and are never shown as findings.
- Constraint: citations link to the file in the source drive; the product never serves the file itself.
- Undecided: pricing, hosting beyond Compose, SSO.

## Brand Commitments
Name: Knowledgebase (kept as the product name on 2026-10-17). No logo, palette, or typeface exists yet. Voice in the UI: plain, direct, states evidence and its absence without hedging.

## Evidence on Hand
- Synthetic demo corpus in `eval/corpus/` (hosting decision, alternative, revision, vacation policy, onboarding guide, emergency plan) and a seeded demo organization with admin, steward, and member accounts.
- Live results: one real Google Drive synced; investigations completed with chunk-level citations (recorded in `HERMES_INTEGRATION.md` and `IMPLEMENTATION_STATUS.md`).
- No customers, testimonials, logos, or usage numbers exist. Future work must not fabricate them.

## Product Principles
- Evidence first: every claim shows where it comes from, and the absence of evidence is said plainly.
- The member's view is the truth: nothing appears that the member could not open in the source.
- Work in the flow: a question is asked and answered without leaving the task; long work shows progress and can be stopped.
- Calm density: operators see many items (links, scopes, records) and need scanability over expression.
- Trust through states: queued, running, verified, purged, quarantined are visible and named consistently.

## Accessibility & Inclusion
Keyboard operable throughout, visible focus, skip link, status regions for polling updates, respects reduced motion. Text content may be in English, Russian, or Kazakh (real drives contain all three), so type and layout must handle Cyrillic.
