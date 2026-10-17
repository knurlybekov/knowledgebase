---
name: Knowledgebase
description: Cited answers from the files a member can open; evidence is the interface.
colors:
  ground: "#f3f4f6"
  surface: "#ffffff"
  surface-2: "#f8f9fb"
  ink: "#111318"
  ink-2: "#4b5160"
  ink-3: "#6b7080"
  line: "rgb(17 19 24 / 0.08)"
  line-strong: "rgb(17 19 24 / 0.16)"
  accent: "#3b5bdb"
  accent-soft: "rgb(59 91 219 / 0.1)"
  accent-fg: "#ffffff"
  ok: "#1f8a4c"
  ok-soft: "rgb(31 138 76 / 0.12)"
  warn: "#b7791f"
  warn-soft: "rgb(183 121 31 / 0.14)"
  bad: "#c43d3d"
  bad-soft: "rgb(196 61 61 / 0.12)"
  info: "#3b5bdb"
  info-soft: "rgb(59 91 219 / 0.12)"
  glass: "rgb(255 255 255 / 0.72)"
  ground-dark: "#09090b"
  surface-dark: "#141417"
  surface-2-dark: "#1b1b20"
  ink-dark: "#f1f1f4"
  ink-2-dark: "#a4a7b4"
  ink-3-dark: "#808498"
  line-dark: "rgb(255 255 255 / 0.08)"
  line-strong-dark: "rgb(255 255 255 / 0.16)"
  accent-dark: "#7c91ff"
  accent-soft-dark: "rgb(124 145 255 / 0.16)"
  accent-fg-dark: "#0a0d1f"
  ok-dark: "#4ccc7f"
  ok-soft-dark: "rgb(76 204 127 / 0.14)"
  warn-dark: "#e0a84a"
  warn-soft-dark: "rgb(224 168 74 / 0.16)"
  bad-dark: "#ef6b6b"
  bad-soft-dark: "rgb(239 107 107 / 0.16)"
  info-dark: "#7c91ff"
  info-soft-dark: "rgb(124 145 255 / 0.16)"
  glass-dark: "rgb(20 20 23 / 0.7)"
typography:
  headline:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
    fontFeature: "'ss01', 'cv11'"
  body-dense:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: "1rem"
    letterSpacing: "0.01em"
  mono:
    fontFamily: "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  cite:
    fontFamily: "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "normal"
rounded:
  xs: "6px"
  sm: "8px"
  md: "10px"
  lg: "12px"
  card: "14px"
  xl: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "32px"
  4xl: "40px"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "36px"
  button-hover:
    backgroundColor: "{colors.surface-2}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "36px"
  button-primary-ask:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "52px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "36px"
  button-ghost-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.bad}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "36px"
  button-danger-hover:
    backgroundColor: "{colors.bad-soft}"
  button-sm:
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "30px"
  button-icon:
    rounded: "{rounded.pill}"
    padding: "0"
    width: "36px"
    height: "36px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "40px"
  field-lg:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    rounded: "{rounded.lg}"
    padding: "0 16px"
    height: "52px"
  field-focus:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  segmented:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.pill}"
    padding: "3px"
  segmented-option:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "30px"
  segmented-option-selected:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "28px"
  chip-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.ink}"
  pill:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "22px"
  pill-ok:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ok}"
  pill-warn:
    backgroundColor: "{colors.warn-soft}"
    textColor: "{colors.warn}"
  pill-bad:
    backgroundColor: "{colors.bad-soft}"
    textColor: "{colors.bad}"
  pill-info:
    backgroundColor: "{colors.info-soft}"
    textColor: "{colors.info}"
  cite:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    typography: "{typography.cite}"
    rounded: "{rounded.xs}"
    padding: "0 4.8px"
    height: "20px"
  cite-linked:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-fg}"
  source-num:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    typography: "{typography.cite}"
    rounded: "{rounded.xs}"
    width: "22px"
    height: "22px"
  claim:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 10px"
  claim-linked:
    backgroundColor: "{colors.accent-soft}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "16px"
  card-source:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.card}"
    padding: "12px"
  unsupported:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.card}"
    padding: "16px"
  top-bar:
    backgroundColor: "{colors.glass}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "8px 12px"
  nav-link:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "32px"
  nav-link-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
  nav-link-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.ink}"
  table-header:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    typography: "{typography.label}"
    padding: "8px 12px"
  table-cell:
    textColor: "{colors.ink}"
    typography: "{typography.body-dense}"
    padding: "10px 12px"
  table-row-hover:
    backgroundColor: "{colors.surface-2}"
  meter:
    backgroundColor: "{colors.line}"
    rounded: "{rounded.pill}"
    height: "4px"
  meter-fill:
    backgroundColor: "{colors.accent}"
    rounded: "{rounded.pill}"
---

# Design System: Knowledgebase

## Overview

**Creative North Star: "Evidence Is the Interface"**

Knowledgebase is a calm, dense operator surface for a team that asks questions mid-task. Every claim on screen carries a numbered citation chip, and the claim and its source card light each other up on hover or focus. The world borrows the register of premium product UI (Linear, Apple): Geist everywhere, a cool silver or near-black ground, white or graphite work surfaces, hairline borders, one soft layered shadow, and a single ink-blue accent that is spent only on primary actions, selection, and the running state.

Density is high but quiet. Tables, status pills, and timelines carry many items without decoration, and state names (Grounded, Candidate, Verified, Running, Withheld) are the loudest words on most screens. The build refuses the flat results list with footnote links, refuses the chat-transcript layout, and never styles an unsupported statement as a finding: it sits in its own dashed-border box, named as unsupported.

Light and dark are two full token sets switched by `data-theme` on `<html>` before first paint. The default follows the system, the toggle in the top bar stores the choice in `localStorage`, and `color-scheme` follows the theme so form controls and scrollbars match.

**Key Characteristics:**
- Claims and sources are linked both ways by data attributes and one small script; hover or focus on either side lights the pair.
- One accent, four state colors, and alpha-tinted soft variants for backgrounds; everything else is a neutral.
- Geist Mono appears only on identifiers, labels, counts, and citation numbers; numerals in data are tabular.
- Hairline borders at 8% and 16% alpha, one soft two-layer shadow for raised surfaces, no hard offset shadows.
- Pills (999px) on every control and status; 10 to 16px radii on fields, cards, and the top bar.
- Icons are inline SVG at 1.5 stroke (1.75 on the primary button arrow), 16 to 20px.

## Colors

Cool neutrals with a faint blue cast, one ink-blue accent, and four state hues; each hue also exists as a low-alpha soft tint for backgrounds.

### Primary
- **Ink Blue** (`accent`, light #3b5bdb; dark #7c91ff): primary buttons, the focus outline, the caret, text selection tint, the selected chip, the active nav link, citation chips and source numbers, the progress meter fill, and the Running and Queued pills. `info` carries the same value and backs `pill-info`.
- **Ink Blue Soft** (`accent-soft`, 10% alpha light, 16% dark): background for a selected chip, the active nav link, a lit claim, citation chips at rest, and the 3 to 4px focus halo on fields and lit source cards.
- **Accent Foreground** (`accent-fg`, white light; #0a0d1f dark): text on a filled accent surface.

### State
- **Verified Green** (`ok` #1f8a4c; dark #4ccc7f): Verified, Completed, Active, Grounded, known timeline stages, the success check in flash messages.
- **Candidate Amber** (`warn` #b7791f; dark #e0a84a): Candidate, pending review, overdue, insufficient or conflicting evidence, unknown timeline stages (dashed dot).
- **Withheld Red** (`bad` #c43d3d; dark #ef6b6b): Withheld, Failed, Error, Timed out, unsupported-statement headings, error codes, the Unlink and Cancel buttons.
- **Slate** (the default `pill` with `surface-2` and `ink-2`): Cancelled, quarantined, obsolete, and any status without a stronger meaning.

### Neutral
- **Silver Ground** (`ground` #f3f4f6; dark Near Black #09090b): the page background.
- **Work Surface** (`surface` white; dark Graphite #141417): cards, fields, buttons, the selected segment.
- **Quiet Surface** (`surface-2` #f8f9fb; dark #1b1b20): segmented-control track, default pill, hover fill for buttons, rows, and nav links.
- **Graphite Ink** (`ink` #111318; dark #f1f1f4): headings, body, field text.
- **Secondary Ink** (`ink-2` #4b5160; dark #a4a7b4): descriptions, excerpts, nav links at rest, table secondary cells.
- **Tertiary Ink** (`ink-3` #6b7080; dark #808498): labels, table headers, timestamps, placeholders, the footer. Raised from the contract's original values after a contrast review.
- **Hairline** (`line`, 8% alpha): card borders, dividers, table rules, the meter track.
- **Hairline Strong** (`line-strong`, 16% alpha): borders on buttons, fields, and chips, the dashed unsupported box, the timeline rail, scrollbar thumbs.
- **Glass** (`glass`, 72% white light; 70% graphite dark): the top bar fill, behind `saturate(160%) blur(18px)`.

### Named Rules
**The One Ink Rule.** The accent is the only chromatic color that is not a state. It marks what the member can act on or what is lit right now; it never decorates.

**The Soft Tint Rule.** A state or accent hue fills a background only through its `-soft` alpha variant, with the full hue as the text or dot on top. Filled pills and chips drop their border (`border-color: transparent`).

**The Named State Rule.** Green, amber, red, and slate always mean verified or healthy, candidate or pending, withheld or failed, and inactive. A new status takes the color of its meaning, not a new hue.

## Typography

**Display Font:** none. The largest type is the 24px page headline.
**Body Font:** Geist (with ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif), weights 400 to 700 from Google Fonts
**Label/Mono Font:** Geist Mono (with ui-monospace, SFMono-Regular, Menlo, monospace), weights 400 to 600

**Character:** One grotesque at close tracking, with the stylistic set `ss01` and `cv11` on for the whole document. Headings tighten (-0.02em) and balance (`text-wrap: balance`); data columns, counts, and ids switch to Geist Mono or tabular numerals so figures align.

### Hierarchy
- **Headline** (600, 1.5rem, 1.2, -0.02em): the one `h1` per page. No larger size exists.
- **Title** (600, 1.0625rem, 1.3, -0.01em): section `h2` (Answer, Your investigations, Connector links) and the large ask field's text size.
- **Body** (400, 0.9375rem, 1.5): the document default; descriptions and claims. Claims use `leading-relaxed` (1.625).
- **Body Dense** (400, 0.8125rem, 1.5): tables, buttons, chips, segmented options, source excerpts, agent activity rows. 0.875rem (`text-sm`) sits between for nav links, the default button, and inline helper text.
- **Label** (500, 0.75rem, 1rem, +0.01em, `ink-3`): field labels, table headers, section labels such as Sources, legend text. Sentence case, never uppercase.
- **Mono** (400, 0.75rem, -0.01em, Geist Mono): source type and version lines, error codes, item ids, activity event types.
- **Cite** (500, 0.6875rem, Geist Mono): numbers inside citation chips and source number badges.
- **Section heading small** (600, 0.875rem): `h3` inside cards (Conflicting evidence, Open questions, Alternatives recorded), colored by state when the list is non-empty.

### Named Rules
**The Mono Boundary Rule.** Geist Mono is for identifiers, labels of record (version, source type), counts, and citation numbers. Sentences are always Geist.

**The Tabular Numeral Rule.** Any number in a data position (table cell, count, timestamp, attempt, percentage) sets `font-variant-numeric: tabular-nums`, through `.tabular`, `code`, `kbd`, or table cells.

**The Sentence Case Rule.** No uppercase labels, no letter-spaced kickers or eyebrows. Labels are small, medium weight, tertiary ink, sentence case.

## Layout

One centered column, 1152px wide (`max-w-6xl`), with a 16px side gutter at every width. The header is sticky with a 16px top inset so the glass bar floats detached from the edge; main content starts 32px below the bar and ends with 64px bottom padding. Prose blocks cap at 672px (`max-w-2xl`) or 768px (`max-w-3xl`); the login card caps at 448px (`max-w-md`).

The working grid is five columns at `lg` (1024px) and above with a 24px gap, split 3 to 2: the ask results, investigations list, and decision timeline take three columns on the left; sources, connected accounts, pending review, and alternatives take two on the right. Below `lg` the grid stacks in source order, and citation chips still link to sources by anchor. Secondary pairs (Conflicting evidence, Open questions) share a two-column grid from `sm` (640px) with a 16px gap.

Spacing is on the 4px grid. Cards pad 12px (`p-3`) for compact items, 16px (`p-4`) for the ask box and status cards, 20px (`p-5`) for answer and empty-state cards, and 24 to 32px for the login card. List rows pad 16px by 12px with hairline dividers between them. Sections sit 24 to 40px apart (`mb-6`, `mb-8`, `mb-10`); a title and its content sit 12px apart (`mb-3`).

Breakpoints in use: `sm` 640px (ask box goes from stacked to row; secondary pair grid), `md` 768px (nav items move from a wrapped second row to inline; the nav scrolls sideways below this with the scrollbar hidden), `lg` 1024px (the 3/2 grid), `2xl` 1536px (the user email shows in the top bar). Long tokens wrap (`overflow-wrap: anywhere` on `main`) so ids and URLs never widen the page.

## Elevation & Depth

Depth comes from three layers of tone plus one soft shadow: the ground, a white or graphite surface with a hairline border, and a quieter inset surface for tracks and hovers. The shadow is a two-layer soft offset with no hard edge; it marks raised and lit surfaces, not every card. The top bar adds translucency (`backdrop-filter: saturate(160%) blur(18px)`) over the glass fill.

### Shadow Vocabulary
- **Soft** (`box-shadow: 0 1px 2px rgb(17 19 24 / 0.06), 0 8px 24px rgb(17 19 24 / 0.06)`; dark `0 1px 2px rgb(0 0 0 / 0.4), 0 8px 24px rgb(0 0 0 / 0.35)`): every `.card` and the glass bar at rest.
- **Raised** (`box-shadow: 0 2px 4px rgb(17 19 24 / 0.08), 0 16px 40px rgb(17 19 24 / 0.1)`; dark `0 2px 4px rgb(0 0 0 / 0.5), 0 16px 40px rgb(0 0 0 / 0.45)`): the ask box, the login card, the pending-review card on hover, and a lit source card.
- **Primary button** (`0 1px 2px rgb(0 0 0 / 0.12), inset 0 1px 0 rgb(255 255 255 / 0.18)`): a thin top highlight on the filled accent button.
- **Selected segment** (`0 1px 2px rgb(0 0 0 / 0.08)`): the checked option in the segmented control.
- **Focus halo** (`0 0 0 4px accent-soft` on fields; `0 0 0 3px accent-soft` plus Raised on a lit source): the accent ring is a box-shadow, not an outline, except for the global `:focus-visible` outline (2px accent, 2px offset, 6px radius).

### Named Rules
**The One Shadow Rule.** Two layers, low alpha, downward. Raised is the same shape at a larger spread; nothing else casts a shadow, and no shadow has a hard edge.

**The Lift Is a State Rule.** A surface rises only when it is the primary surface (ask box, login) or when it is lit by hover or focus. A lit source lifts 1px (`translateY(-1px)`) with a 3px accent halo over the Raised shadow, in 180ms.

## Shapes

Two families: pills and soft rectangles. Every control is a pill (999px): buttons, segmented control and its options, filter chips, status pills, nav links, the meter, and scrollbar thumbs. Content containers are soft rectangles: 6px on citation chips, source numbers, and the focus outline; 8px on inline alerts; 10px on fields and the claim highlight; 12px on the large ask field; 14px on cards (`--radius`); 16px on the floating top bar.

Borders are 1px hairlines: 8% alpha on cards and dividers, 16% on interactive edges (buttons, fields, chips). The unsupported-statements box is the one dashed border in the system, 1px at 16% alpha on a transparent background, so it reads as set apart rather than as a finding. The timeline rail is a 1px vertical line with 12px dots: filled green for known stages, dashed amber for unknown, red border for errors. The status dot inside a pill is a 6px circle in `currentColor`; the Running pill pulses it over 1.6s.

## Components

### Buttons
- **Shape:** pill (999px), 36px tall, 14px side padding, 0.875rem medium; `btn-sm` is 30px tall at 0.8125rem with 12px padding; `btn-icon` is a 36px square.
- **Default:** work surface, 16% hairline border, graphite text. Hover: quiet surface with the border darkened to `ink-3`. Active: `scale(0.98)`. Disabled: 50% opacity.
- **Primary:** accent fill, accent foreground text, no border, the thin inset top highlight. Hover: `color-mix(in oklab, accent 88%, black)`. The ask-box variant is 52px tall (`h-13`) with 20px padding and a 24px round arrow badge at 15% white.
- **Ghost:** transparent, secondary ink. Hover: quiet surface, graphite text. Used for Log out and the theme toggle.
- **Danger:** default shape with `bad` text. Hover: `bad-soft` fill, no border. Used for Cancel and Unlink.
- **Transitions:** background, border, transform, and shadow over 180ms on `cubic-bezier(0.32, 0.72, 0, 1)`.

### Chips
- **Style:** pill, 28px tall, 12px padding, 0.8125rem, 16% hairline border, secondary ink, transparent fill. The checkbox is visually hidden inside the label.
- **Selected:** `accent-soft` fill, border transparent, graphite text. Focus: 2px accent outline at 1px offset. Used as source filters (Google Drive, SharePoint).

### Segmented control
- **Style:** a pill track on the quiet surface with a hairline border and 3px padding; options are 30px pills at 0.8125rem medium in secondary ink. The radio is visually hidden.
- **Selected:** work surface fill, graphite text, the 1px selected-segment shadow. Disabled options sit at 45% opacity. Used for Quick Search and Deep Investigation.

### Status pills
- **Style:** pill, 22px tall, 8px padding, 0.75rem medium, a 6px leading dot in `currentColor` at 80% opacity. Default: quiet surface, secondary ink, hairline border.
- **Variants:** `pill-ok`, `pill-warn`, `pill-bad`, `pill-info` take the soft tint as fill, the full hue as text, and drop the border. `pill-live` pulses the dot (1.6s, infinite) and marks Running only.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** work surface with an 8% hairline border and the Soft shadow. `raised` adds the Raised shadow for the ask box and login.
- **Internal Padding:** 12px for source cards and timeline quotes, 16px for status and the ask box, 20px for answers and empty states. Lists inside a card use `overflow-hidden` and hairline row dividers; rows hover to the quiet surface in 150ms.
- **Unsupported box:** transparent, 1px dashed 16% border, 14px radius, 16px padding, a red small heading and a tertiary explainer line.

### Inputs / Fields
- **Style:** 40px tall, 10px radius, 16% hairline border, work surface, 14px padding, inherits the body font; placeholder in tertiary ink. `field-lg` is 52px tall at 1.0625rem with a 12px radius for the ask box. Selects hide the native arrow and draw a 1.5-stroke chevron.
- **Hover:** border to `ink-3`.
- **Focus:** no outline; border to accent plus a 4px `accent-soft` halo, 180ms.
- **Error:** the login error is a separate line, 8px radius, `bad-soft` fill, `bad` text, `role="alert"`.

### Navigation
- **Top bar:** sticky, 16px inset from the top and sides, a 16px-radius glass surface (72% white or 70% graphite, saturate 160% blur 18px) with hairline border and Soft shadow, 8px by 12px padding. Left: a 20px inline-SVG book mark, the product name in semibold tight tracking, a slash and the organization in secondary ink. Right: the user email (tertiary, from 2xl), Log out (ghost small), the theme toggle (ghost icon, sun or moon at 1.5 stroke showing the theme you would switch to).
- **Nav links:** 32px pills, 0.875rem medium, secondary ink. Hover: quiet surface, graphite. Current page: `accent-soft` fill, graphite text, `aria-current="page"`.
- **Mobile:** below `md` the link list wraps to a full-width second row that scrolls sideways with the scrollbar hidden.
- **Skip link:** visually hidden until focus, then a fixed pill on the work surface with the Raised shadow.

### Evidence pair (signature)
The answer is an ordered list of claims on the left (3 of 5 columns) and numbered source cards on the right (2 of 5). Each claim is a `.claim` row (10px radius, 8px by 10px padding, pulled 10px into the margins so the highlight bleeds past the text) with `data-ev="src-1 src-2"` and `tabindex="0"`, followed by its `.cite` chips: 20px mono accent numbers on `accent-soft`, 6px radius, lifted 0.15em. Each source is a `.source` card with `data-ev-id`, a 22px `.source-num` badge in the same style, a linked title, a mono source-type and version line, and a 4 or 5 line clamped excerpt.

Hover or focus on either side sets `is-linked` on the claim, its chips, and its sources: the claim fills `accent-soft`, chips invert to the accent fill, and the source gains an accent border, a 3px halo over the Raised shadow, and a 1px lift. Clicking a chip scrolls its source to center and focuses it. All transitions are 180ms on the spring ease; under `prefers-reduced-motion: reduce` every transition and animation collapses to 0.01ms.

### Data tables
- **Style:** full width, 0.8125rem, separate borders. Headers are Label type in tertiary ink with a hairline bottom rule and no wrapping. Cells pad 10px by 12px, top aligned, tabular numerals, hairline rules between rows and none after the last. Numeric columns are `.num` and right aligned; ids and error codes are `.mono`, errors in `bad`.
- **Hover:** row to the quiet surface in 150ms.
- **Empty:** one centered tertiary line with 32 to 40px vertical padding.

### Progress meter
A 4px pill track in `line` with an accent fill whose width animates over 400ms. Sits under the investigation status row; `aria-hidden`, with the counts spoken by the row text.

### Timeline rail
`.rail` adds 28px left padding and a 1px vertical line at 16% alpha; each item carries a 12px `.rail-dot` on the work surface with a 2px border in tertiary ink. `is-known` fills green, `is-unknown` dashes amber, an error borders red. Stage items hold evidence as 12px-padded quote cards with a mono footer.

### Disclosure
`<details class="disclosure">` hides the native marker and uses a 16px chevron that rotates 90 degrees over 180ms when open. Used for Agent activity.

## Do's and Don'ts

### Do:
- **Do** attach a numbered `.cite` chip to every claim and give it a matching `.source` card with `data-ev` and `data-ev-id`; a claim without a passage goes in the dashed `.unsupported` box, never in the answer list.
- **Do** spend the accent only on primary actions, the selected or current item, the lit evidence pair, focus, and the Running state.
- **Do** set states through the four pill variants with their fixed meanings (green verified or healthy, amber candidate or pending, red withheld or failed, slate inactive) and reuse the exact words already on screen.
- **Do** use Geist Mono and tabular numerals for ids, version lines, counts, timestamps, and numeric table columns.
- **Do** keep every control a pill and every container a 10 to 16px soft rectangle; cards are 14px.
- **Do** build icons as inline SVG at 1.5 stroke, round caps and joins, 16 to 20px, `aria-hidden`.
- **Do** transition state over 180ms on `cubic-bezier(0.32, 0.72, 0, 1)` and let the reduced-motion rule collapse it.
- **Do** write both token sets: any new color is added to `:root` and `[data-theme="dark"]` and mapped in `@theme inline`.

### Don't:
- **Don't** render an answer as a flat results list with footnote links or as a chat transcript; claims left, sources right, linked both ways.
- **Don't** style an unsupported statement with a pill, a card shadow, or a citation chip.
- **Don't** add a second accent hue, a gradient, or a hard offset shadow; the Soft and Raised shadows are the whole vocabulary.
- **Don't** set labels, kickers, or table headers in uppercase or letter-spaced type, and do not add an eyebrow above a headline.
- **Don't** use Geist Mono for sentences, or a system display face anywhere.
- **Don't** add a border and a tinted fill at the same time on a pill or chip; a tinted fill means `border-color: transparent`.
- **Don't** use type larger than the 24px headline; this is an operator surface, not a landing page.
