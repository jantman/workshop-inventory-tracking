# Implementation Plan: Capture Reads the "About this item" Bullets

**Branch**: `issues/92` | **Date**: 2026-08-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-capture-about-this-item/spec.md`

## Summary

Amazon's **About this item** bullets are the only place some listings publish their physical facts —
on `B01N4OSKWE` every dimension the product has is in those five bullets and nowhere else — and the
capture agent has never read them. Add a reader that takes the `li` elements out of
`#feature-bullets` and emits them as one specification row named `About this item`, one bullet per
line, placed first in the reading so the existing first-occurrence-wins fold resolves any name
collision in its favor.

The change is one new function and two edited lines in `app/static/js/capture-agent.js`, plus
fixture and test work. No Python changes, no schema change, no migration, no new dependency.

Two of issue #92's premises did not survive a live inspection of the markup on 2026-08-19 and the
design follows what was actually there:

- **"See more product details" is not a hidden `li`.** On all three listings probed it is a visible
  sibling `div` after the `<ul>`. Reading `li` excludes it — and excludes the `<h2>About this
  item</h2>` heading that sits inside the same container and that the issue does not mention.
- **A visibility test is not implementable anyway.** `canonicalDocument()` hands the reader a
  detached `DOMParser` document with no layout and no stylesheets, so `offsetHeight` is 0 and
  `getComputedStyle` is meaningless. FR-005 is met structurally or not at all.

See [research.md](research.md) for the observed markup and both corrections.

## Technical Context

**Language/Version**: ES5-compatible browser JavaScript (the capture agent runs in the operator's
browser on a vendor's page, unbundled and untranspiled — the file uses `const`/`let` and no
`async`/arrow-in-class syntax beyond what it already contains). Python 3.13 for the test suite.

**Primary Dependencies**: None added. The agent depends on nothing but the DOM; the tests use
Playwright, already present.

**Storage**: MariaDB, `product_specifications`. **No schema change and no Alembic revision** — see
[data-model.md](data-model.md).

**Testing**: `nox -s tests` (no new coverage expected) and `nox -s e2e` (where all of this feature's
coverage lands), against the hand-written fixtures in `tests/e2e/fixtures/`.

**Target Platform**: Chrome on the operator's LAN workstation, reading amazon.com; Flask app on the
same LAN.

**Project Type**: Server-rendered Flask web application with a single injected client-side script.

**Performance Goals**: None. The reader is one `querySelectorAll` over a container of five or six
list items, inside an operation already dominated by an 8-to-15-second gallery fetch. Principle I
forbids optimizing without a measurement, and there is nothing here to measure.

**Constraints**: The reader must behave identically against a detached parsed document and against
the live `document` (the fallback path), and must not be able to throw — a selector that stops
matching costs the bullets row and nothing else.

**Scale/Scope**: One function, one call site, two fixtures, roughly six e2e assertions. Single user,
LAN-only, as ever.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design. Both passes below.*

| Principle | Verdict | Note |
|-----------|---------|------|
| **I. Simplicity First** | **PASS** | One function, no abstraction, no configuration. The temptation this feature carries is a general "is this element visible" facility; research.md kills it twice over — it is not implementable on the detached document, and no bullet on any probed listing is hidden. Also declined: a hidden-marking-class filter, as machinery for a case with no observed instance. |
| **II. Layered Architecture Boundaries** | **PASS** | Nothing crosses a layer. No route, service, storage or model file is touched; the change is entirely on the vendor side of the payload boundary, which the payload contract already defines. |
| **III. Exact Numerics** | **PASS (N/A)** | No measured quantity is parsed or computed. The bullets are stored as text exactly as the listing wrote them — including `15 x 7 x 7mm/0.59"x0.28"x0.28"`, which is deliberately *not* interpreted into dimensions. |
| **IV. Test Discipline Through Nox** | **PASS, with obligations** | All coverage runs through `nox -s e2e` with a ≥15-minute timeout. No new pytest marker. Every new wait must be on observable state — the capture flow's existing helpers already establish the landing page, and `#product-specifications` is server-rendered, so no `count()`/`text_content()` read may precede an `expect()` that establishes its region. |
| **V. MariaDB Is the Source of Truth** | **PASS** | No schema change, so no migration. Stated in data-model.md so that "where does the bullets text live" cannot be answered by inventing a column. |
| **VI. Item Lifecycle and History Invariants** | **PASS (N/A)** | Inventory items are untouched. This is the product catalog. |
| **Operating Context** | **PASS** | No sanitization layer is added. The prose reader strips `style`/`script` because a stylesheet is not writing, not because a vendor is an attacker — that distinction is already made in the file. |
| **Workflow: branch and PR** | **Required** | Non-trivial code change → feature branch `issues/92`, merged via PR. |
| **Workflow: screenshots** | **Triggered, expected no-op** | `app/static/js/**` is touched. `capture-agent.js` is never loaded by an application template, so no screenshot can depend on it; `nox -s screenshots_verify` is run to establish that rather than assert it. |

**Post-Phase-1 re-check**: unchanged. The design added no entity, no interface, and no dependency.
The only thing Phase 1 added was the decision to emit the row *first* rather than last, which is one
statement inside an existing loop and reduces work rather than adding it — it makes FR-009's
collision case fall out of the existing fold instead of needing its own rule.

**Complexity Tracking**: not applicable. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/020-capture-about-this-item/
├── spec.md                      # /speckit-specify output
├── plan.md                      # This file
├── research.md                  # Phase 0 — live markup probe, two corrections to the issue
├── data-model.md                # Phase 1 — no schema change, and why that is the point
├── quickstart.md                # Phase 1 — how to validate, including the manual real-listing check
├── contracts/
│   ├── listing-payload.md       # The payload boundary; version stays 1
│   └── bullets-reader.md        # The new function's obligations
├── checklists/
│   └── requirements.md          # Spec quality checklist (all pass)
└── tasks.md                     # /speckit-tasks output — NOT created by /speckit-plan
```

### Source code (repository root)

```text
app/
└── static/js/
    └── capture-agent.js         # THE ONLY PRODUCTION FILE THIS FEATURE CHANGES
                                 #   + BULLET_CONTAINER / bulletsRow()
                                 #   ~ specificationsFrom(): seed the output and the fold

tests/e2e/
├── fixtures/
│   ├── amazon_listing.html      # + an About this item block in the real observed shape
│   ├── amazon_listing_aplus.html# + the same, so both description forms are covered
│   └── amazon_listing_markup_only.html   # left without one: the no-bullets case (US4)
└── test_product_page_capture.py # + the new scenarios; ~ the exact-order payload assertion
```

**Structure Decision**: no new module, package or directory. The reader belongs in
`capture-agent.js` next to `specificationsFrom()` because that is the function that owns "what the
product-information rows are", and this is one more source of them. Putting it anywhere else would
split one question across two files.

## Approach

### The reader

A new `bulletsRow(doc)` returning `{name, value}` or `null`, obligations as set out in
[`contracts/bullets-reader.md`](contracts/bullets-reader.md). It reads `li` elements within the
bullet container, runs each through the file's existing `proseOf` so the #91 stripping and line
handling apply unchanged, drops the empty ones, and joins with a single `\n` — one `\n`, not two,
because these are list items and `proseFrom` already emits paragraph breaks around a `LI`.

### The call site

`specificationsFrom()` seeds both its `entries` array and its `seen` map with the bullets row before
the container loop. Seeding the fold — not merely prepending to the array — is what makes FR-009 and
contract C-5 true: without it, a detail table publishing an `About this item` row would produce a
second one.

### The fixtures

The observed shape goes into two of the three fixtures verbatim: the `hr`, the `h2` heading, the
`ul.a-unordered-list` of `li.a-spacing-mini > span.a-list-item`, and the trailing
`div.a-section` holding "See more product details". The heading and the trailing div are not
decoration in the fixture — they are the two things the reader must exclude, and a fixture without
them tests nothing. `amazon_listing_markup_only.html` deliberately gains no bullet list, so US4 has a
case.

### What is not built

- No visibility filtering, and no hidden-class filtering (research.md §1).
- No parsing of bullet text into fields. `B01N4OSKWE`'s bullets are full of `Name: Value; Name:
  Value` and it is tempting; the spec rules it out and it is a much harder problem.
- No de-duplication between the bullets and the description.
- No display or edit work — #91 already did all of it, confirmed in the tree (research.md §3).
- No Python change of any kind.

## Risks

| Risk | Bound |
|------|-------|
| Amazon renames `#feature-bullets` | FR-011: the step is independent and optional; the capture loses one row. The hand-written fixture cannot detect it — this is stated in research.md rather than mitigated, as it was for the original capture feature. |
| The `\n` vs `\n\n` choice reads wrong in practice | Visible immediately on the first real capture (quickstart step 4). One-character fix. |
| The exact-order payload assertion gets loosened instead of updated | Called out in research.md §5 and quickstart §2. It is #91's "nothing else moved" guard and is what makes FR-010 testable. |
| Screenshot churn confuses the gate | Measure the diff before committing any image; do not regenerate reflexively. |
