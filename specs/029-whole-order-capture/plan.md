# Implementation Plan: Whole-Order Capture for Every Vendor

**Branch**: `issues/122` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-whole-order-capture/spec.md`

## Summary

Close the last of the three order-capture gaps — Amazon — and stop having three copies of the
same feature while doing it.

The approach in one line: **unify the two shipped order captures onto one flow parameterized by
a small per-vendor value, then add Amazon as a third such value plus a reader in the capture
agent.**

Four things make this cheaper than it sounds, and all four were established by reading the code
rather than assumed:

1. **The seam already half exists.** `OrderCaptureReview` and `ReviewedLine` are already shared
   by both flows. What is duplicated is the machinery *around* them — the pairing lookup, the
   per-line review, the confirmation orchestration, the templates and the routes — and those
   differ from each other in named, enumerable ways (research.md §9).
2. **The vendor-specific remainder is eight things**, listed in research.md §9 and frozen as
   FR-036. Everything else is one implementation.
3. **Amazon's page is the most stable of the three.** It anchors on semantic `data-component`
   attributes rather than on classes — no build hashes, unlike McMaster's product pages
   (research.md §3).
4. **No schema change.** Every column Amazon needs already exists, added by the two predecessor
   features (research.md §13). This is the first of the three not to ship an Alembic revision.

**Order of work is the reverse of the story priorities, deliberately.** US3 (consolidate) is P3
by value and first by sequence, because building Amazon as a third copy and then merging three
is strictly more work than merging two and extending the result — and it would triple the
surface a defect has to be fixed on in between. The spec says so in its assumptions; this plan
acts on it.

**The one open input**: how a quantity greater than one renders on an Amazon order page. Ten
consecutive orders contained no such line, so it is closed by one task against one real
multi-quantity order. It cannot corrupt anything — the quantity is on the review, editable,
before a row is written (research.md §6). Everything else in this plan is fixed.

## Technical Context

**Language/Version**: Python 3.13 (server); ES5-compatible browser JavaScript (the capture
agent — it runs in the operator's browser on a vendor's page and has no build step)

**Primary Dependencies**: Flask, SQLAlchemy, Alembic, PyMySQL, Jinja2 — all present. **No new
dependency**, and none is warranted: reading a DOM happens in the browser, and writing rows
happens through the service that already writes them.

**Storage**: MariaDB via `MariaDBStorage`; SQLite through the same interface under unit test.
**No schema change** — see research.md §13.

**Testing**: pytest through `nox` (`tests`, `e2e`, `lint`); Playwright for e2e. No new pytest
markers, so `pytest.ini` is untouched under `--strict-markers`.

**Target Platform**: Flask app on the LAN, no login, single operator. The agent runs in the
operator's own browser on `amazon.com`.

**Project Type**: Server-rendered Flask web application with a small amount of vanilla
JavaScript. No SPA, no build pipeline, no bundler.

**Performance Goals**: none new. The order review is one page render over an order's worth of
lines; the captured-orders list is one aggregate over `purchases`. Per Constitution I, no
caching or batching without a measurement.

**Constraints**: the bookmarklet's text cannot change (the operator would have to re-drag it),
so everything new goes in the agent, which cache-busts on load. Extraction is per-field and
must never throw. Nothing may be written before the operator confirms.

**Scale/Scope**: one operator; orders of 1–30 lines; a few orders a week. Roughly 350 lines of
duplicated service code collapse to one implementation; three review/order templates collapse to
one pair; one new reader, one new vendor value, one new list screen.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design. Both passes recorded.*

| Principle | Verdict | Note |
|---|---|---|
| **I. Simplicity First** | **PASS, with one justified exception** | The consolidation introduces an abstraction. See Complexity Tracking — the rule bars generalizing over *one* implementation; this is three, two already shipped and reviewed, and the differences are measured (research.md §9) rather than guessed. No new dependency, no caching, no async, no background work, no config knob. |
| **II. Layered Architecture** | **PASS** | Business logic stays on `CatalogService`; the per-vendor value lives in `app/services/`; routes stay thin and gain no ORM query. The whole-order write stays in one session on the service, for the reason both existing captures give. |
| **III. Exact Numerics** | **PASS** | Prices parse to `Decimal` and go through the existing `price_to_cents` (ROUND_HALF_UP) quantizer. No `float` anywhere on the path. Amazon needs no division at all (research.md §5). |
| **IV. Test Discipline** | **PASS** | Everything through `nox`. No new markers. The existing DigiKey and McMaster suites are the regression gate and are run **unedited** (research.md §14). E2E waits on rendered state — pattern C — never on a clock. Templates change, so `nox -s screenshots` must be regenerated and committed. |
| **V. MariaDB Source of Truth** | **PASS, trivially** | No schema change, so no revision (research.md §13). The captured-orders list is derived, not stored. |
| **VI. Item Lifecycle Invariants** | **N/A** | This feature touches products and purchases, not inventory items or JA IDs. No add/move/shorten/edit path is involved. |
| **Threat model** | **PASS** | No auth, no hardening, no sanitization layer. The new form is same-origin and CSRF-protected like every other; `/api/capture` stays exempt because it is cross-origin from the vendor's page, exactly as today. Nothing personal is read off the order page (research.md §8). |
| **Workflow** | **PASS** | Feature branch `issues/122`, merged by PR. Screenshots regenerated with the UI change. |

**Post-Phase-1 re-check**: unchanged. The design in data-model.md and contracts/ adds one frozen
dataclass, one module, one derived query and one template pair, and deletes more than it adds.
No gate moved.

## Project Structure

### Documentation (this feature)

```text
specs/029-whole-order-capture/
├── plan.md              # This file
├── research.md          # Phase 0 — the Amazon investigation and the duplication measurement
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── order-vendor.md      # The consolidation seam — what a vendor supplies
│   ├── capture-payload.md   # The Amazon order payload the agent posts
│   └── routes.md            # HTTP routes: new, changed, and retired
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── models.py                     # + AmazonOrder / AmazonOrderLine payload types
│                                 # ~ DigiKeyCaptureResult + McMasterCaptureResult -> OrderCaptureResult
├── catalog_service.py            # ~ the consolidation: one review_order / capture_order_lines
│                                 #   pair replacing two of each, plus the shared helpers
├── services/
│   └── order_vendors.py          # NEW — the three OrderVendor values
├── product/
│   └── routes.py                 # ~ /api/capture grows an Amazon-order branch
│                                 # + /products/amazon/orders/capture
│                                 # ~ order detail routes converge on one
│                                 # + /products/orders  (the captured-orders list)
│                                 # ~ _receive_url states the rule once
├── static/js/
│   └── capture-agent.js          # ~ pageKind takes the location, not just the path
│                                 # + the Amazon order reader
└── templates/product/
    ├── order_review.html         # NEW — replaces digikey_order_review + mcmaster_order_review
    ├── order.html                # NEW — replaces digikey_order + mcmaster_order
    └── orders.html               # NEW — the captured-orders list

tests/
├── unit/
│   ├── test_amazon_capture.py    # NEW
│   ├── test_order_vendors.py     # NEW — the seam itself
│   └── test_digikey_*.py, test_mcmaster_*.py   # UNCHANGED — the regression gate
└── e2e/
    ├── test_amazon_order.py      # NEW
    ├── test_orders_list.py       # NEW
    ├── fixtures/amazon_order*.html   # NEW — scrubbed, recommendation markup retained
    └── test_digikey_*.py, test_mcmaster_*.py   # UNCHANGED — the regression gate
```

**Structure Decision**: the existing layout is kept exactly. The one new module,
`app/services/order_vendors.py`, follows the constitution's stated placement for shared services
(`app/services/`). No new layer, no new package, no new directory.

## Phases

**Phase A — consolidate (US3, no user-visible change).** Introduce `OrderVendor`; collapse the
paired service helpers, the two result types, the two review templates and the two order screens
onto one implementation each; state the receiving rule once. **Gate: the existing DigiKey and
McMaster suites pass unedited.** Nothing else may land until that is true.

**Phase B — Amazon (US1).** The agent's dispatch change and Amazon reader; the payload types; the
third `OrderVendor`; the `/api/capture` branch and the confirm route; fixtures and tests.
Includes the one task that closes the qty>1 question.

**Phase C — receiving and the list (US2, US3's remainder).** Receiving from the order screen for
any vendor; the captured-orders list and its navigation entry; screenshots.

## Complexity Tracking

> Filled because the Constitution Check records one justified exception.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| An abstraction (`OrderVendor`) over the order-capture flow, against Principle I's "no abstraction for a single implementation" | There are **three** implementations, not one. Two have shipped and been through review, so the eight points of variation are measured (research.md §9), not anticipated. The duplication has already cost real defects: two of the fixes in review of PR #123 were the McMaster copy of behaviour the DigiKey copy had already had corrected. FR-037 is the standing test that the seam is in the right place. | **Leave it duplicated and write Amazon as a third copy**: rejected by US3, and it would make three places for every future fix instead of two. **A class hierarchy**: more machinery than the variation warrants — this is data and a few callables, not polymorphic behaviour needing dispatch through a deep call tree. **Consolidate templates only**: the templates are the least dangerous part; the orchestration is where the defects were. |
