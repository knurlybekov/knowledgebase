---
version: 1
slug: "templates-base-html"
primary_target: "templates/base.html"
related_targets: ["templates/web/dashboard.html","templates/web/search.html","templates/investigations/_status.html","templates/decisions/detail.html","templates/connectors/index.html","templates/web/administration.html","templates/accounts/login.html"]
---

# Surface brief: application shell and all pages

Scope: redesign of the whole server-rendered app (base shell, login, dashboard, search and answers, investigations, decisions, connectors, administration). Visitor mode: Operate. Code-led. Direction pinned by the owner on 2026-10-17: premium product UI (Linear and Apple language) held to Operate's limits: the world lends type, palette, density, and one signature move; navigation and controls stay standard.

Audience and job: members of a small team ask a question mid-task and need a cited answer; stewards review candidate decision records; admins watch sync health. Success: the answer and its sources are read in one glance, states (queued, running, verified, purged, quarantined) are unmistakable, dense tables scan fast.

Constraints: Django templates, HTMX polling, Tailwind v4 (django-tailwind-cli), no JS framework; small vanilla scripts allowed. Light and dark themes with a toggle and system default. Keyboard operable, visible focus, status regions, reduced motion respected. Cyrillic text in real content. No fabricated numbers or customers.

## Direction contract

THESIS: Evidence is the interface. Every claim on screen carries its numbered citation, and statement and source light each other up. The surface refuses the category default of a flat results list with footnote links and refuses the chat-transcript layout.

OWN-WORLD: Geist for everything, Geist Mono only for ids, labels, and counts. Light: cool silver ground (#f3f4f6), white work surfaces, graphite text (#111318). Dark: near-black ground (#09090b), graphite surfaces (#141417), off-white text. One ink-blue accent (#3b5bdb light, #7c91ff dark) for primary actions, selection, running state. State colors: verified green, candidate amber, purged and withheld red, quarantined slate. Hairline borders at 6 to 8% alpha; one soft offset shadow (0 1px 2px, 0 8px 24px at low alpha) for raised surfaces; radii 12 to 16px on cards, pills only on controls. Tabular numerals in data.

STORY: A member lands on the ask box, types, and reads an answer whose sentences are numbered to their passages. When a claim lacks evidence it is set apart, named as unsupported, and never styled as a finding. A steward sees pending records first. An admin sees health and backlog without opening a table.

FIRST VIEWPORT (dashboard, 1440 wide): a floating glass top bar detached from the top edge holding the product name with the organization, the four nav items, the user, and the theme toggle. Below, the ask box spans the content width as a single raised surface: one input, a segmented control Quick Search | Deep Investigation, source chips, one primary button. Under it a two-column region: left, "Your investigations" as a compact list with status pills and age; right, "Connected accounts" with provider, account, last sync, and a quiet health line, and for stewards a "Pending review" count linking to decisions. Primary action: the ask box button.

FORM: Answer surfaces as a two-column evidence layout: claims left, sources right, with numbered chips; collapses to stacked on narrow screens with chips still linking by anchor. Signature interaction: hovering or focusing a claim raises its source card (ring in the accent, slight lift) and hovering a source raises its claims; implemented with data attributes and one small script, 180 ms ease-out, no motion under reduced motion. Position on the ordered list: first of three (others: timeline-first and source-first layouts). seed: none (unavailable). No concept roll ran: the owner pinned the direction in the build-frontend interview on 2026-10-17, and a user-pinned direction beats the roll.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
