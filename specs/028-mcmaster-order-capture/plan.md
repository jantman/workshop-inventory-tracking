# Implementation Plan: McMaster-Carr Order and Product Capture

**Branch**: `028-mcmaster-order-capture` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/028-mcmaster-order-capture/spec.md`

## Summary

Capture a whole McMaster-Carr order, and a single McMaster part, by reading the page the
operator is looking at — because issue #119 rules out API access and the bookmarklet is what is
left.

The approach in one line: **the agent grows a McMaster reader and a page dispatch; the order it
reads rides the existing `/api/capture` endpoint as one extra form field; the server renders a
review that carries what was read; and confirming it writes purchases the same way DigiKey's
capture already does.**

Four things fall out of "the vendor cannot be re-read", and they are what distinguishes this
from feature 024:

1. **The review is the only record of the read.** DigiKey's confirm step re-fetches the order
   and treats it as the authority; there is nothing here to re-fetch, so the payload is carried
   through the confirmation in a hidden field and what the review displayed is what gets
   written (FR-006).
2. **The bookmarklet's text cannot change.** It is a `javascript:` URL sitting in the operator's
   browser, so a new endpoint or a new data attribute would mean re-dragging it. Everything new
   goes in the agent, which cache-busts itself on every load.
3. **Dispatch keys on the path, not the host** — which is also the only thing that makes the
   McMaster readers testable end to end, since the e2e harness serves vendor fixtures from the
   application's own origin.
4. **Extraction failure is per-line and must be *stated*.** A dead selector costs one field on
   Amazon; on an order page it can cost one field on fourteen lines, or the line count itself.

One schema change: `purchases.digikey_line_number` becomes `purchases.order_line_number`, since
FR-014 needs for McMaster exactly what that column already does for DigiKey.

**The one open input**: no selector can be written until two saved McMaster pages exist as
fixtures. That is an input, not a spec gap — everything else in this plan is fixed by the spec
and unaffected by which class McMaster hangs a price on. See research.md §5 and quickstart.md.

## Technical Context

**Language/Version**: Python 3.13 (server), ES5-compatible browser JavaScript (the capture
agent — it runs in the operator's browser on a vendor's page and has no build step)

**Primary Dependencies**: Flask, SQLAlchemy, Alembic, PyMySQL, Jinja2 — all present. **No new
dependency**, and none is warranted: reading a DOM happens in the browser and writing rows
happens through the service that already writes them.

**Storage**: MariaDB via `MariaDBStorage`; SQLite through the same interface under unit test

**Testing**: pytest through `nox` (`tests`, `e2e`, `lint`); Playwright for e2e. No new pytest
markers, so `pytest.ini` is untouched under `--strict-markers`.

**Target Platform**: Flask app on the LAN, no login, single operator. The agent runs in the
operator's own Chrome/Firefox on `mcmaster.com`.

**Project Type**: Server-rendered Flask web application with a small amount of vanilla
JavaScript. No SPA, no build pipeline, no bundler.

**Performance Goals**: A capture is a thing the operator clicks and waits a couple of seconds
for. Extraction is local to the browser and instant; the confirm is one transaction. The only
slow part is image retrieval on a product capture, which is already synchronous and already
takes eight to fifteen seconds for a full gallery — expected, not a defect (007 research).

**Constraints**: The vendor page is HTTPS and this app is plain HTTP on the LAN, so the
transport must stay a form POST into a new tab — a `fetch` is refused as mixed content before
CORS or CSRF are ever consulted. Prices are `Decimal` end to end, including in JSON transit
(strings on the wire). Nothing is written before the operator confirms.

**Scale/Scope**: One operator. An order is a dozen or two lines, a few times a year. Roughly:
one Alembic revision, two payload dataclasses, four service methods, three new routes plus one
branch on an existing one, one new reader section in the capture agent, three templates, two
saved page fixtures.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design. Both passes below.*

| Principle | Verdict | How this design satisfies it |
|---|---|---|
| **I. Simplicity First** (NON-NEGOTIABLE) | **PASS** | No new dependency, no configuration knob, no plugin point, no background job, no cache. No vendor abstraction is introduced: McMaster gets its own service methods next to DigiKey's rather than a shared `OrderCapture` protocol built by editing a working write path (research.md §7). The order payload reuses the endpoint that already exists rather than adding one. |
| **II. Layered Architecture Boundaries** | **PASS** | Payload parsing and the pack arithmetic are frozen dataclasses in `app/models.py`; all business logic is in `app/catalog_service.py`; the new routes forward form values and render what the service returns. **No ORM query and no raw SQL in a route.** The one existing helper being changed (`_receive_url`) reads attributes off objects the service already handed it. |
| **III. Exact Numerics** | **PASS** | Prices cross the wire as **strings** — JSON's only number type is an IEEE double, and a float in transit is still a float. `Decimal` from parse to storage, quantized by the existing `price_to_cents` (`ROUND_HALF_UP`). The pack division is `Decimal / int`. Quantities are integers because they are counts. No `float` appears anywhere on this path. |
| **IV. Test Discipline Through Nox** | **PASS** | Unit tests with the network blocked and fixtures built through `tests/conftest.py`; e2e through `nox -s e2e` with a 15-minute timeout, run detached. No new markers. Every new wait names an element — the review's landing is a full navigation, so the form's presence is the completion signal (pattern C). **Zero `wait_for_timeout` added**, and the run leaves the working tree clean. |
| **V. MariaDB Is the Source of Truth** | **PASS** | The one schema change ships as an Alembic revision applied through `manage.py db upgrade`, with a `downgrade` that is exercised in both directions before it is trusted. The ORM column definition must match the revision exactly — the unit suite uses `create_all` and never runs Alembic, so drift passes `nox -s tests` and fails on the real database. |
| **VI. Item Lifecycle and History Invariants** | **PASS — not touched** | This feature lives entirely in the product catalog (`products`, `purchases`, `product_identifiers`). It does not read or write `InventoryItem`, JA IDs, active-row filtering, shortening history or parent-child links. |

**Operating context**: LAN-only, single operator, no login. The payload declares its own vendor
name and the server trusts it (research.md §4) — appropriate here, where the threat model has no
anonymous attacker and the alternative costs the feature its end-to-end test coverage.

**Post-design re-evaluation**: unchanged. Phase 1 added no dependency, no abstraction and no
table. The one thing worth naming is the branch on `/api/capture` — one endpoint answering two
payload shapes. It is not a violation: the route already accepts a capture and renders a page
for the operator to confirm, and falling through on a payload it cannot read is the contract it
has had since 007 FR-007, not new code. The alternative — a second endpoint — would change the
bookmarklet's text and break FR-034.

## Project Structure

### Documentation (this feature)

```text
specs/028-mcmaster-order-capture/
├── plan.md                       # This file
├── spec.md                       # The specification
├── research.md                   # Phase 0 — 13 decisions
├── data-model.md                 # Phase 1 — payload types, the column rename, what a capture writes
├── quickstart.md                 # Phase 1 — how to validate, and what cannot be validated here
├── contracts/
│   ├── capture-payload.md        # Phase 1 — the agent/server machine boundary
│   └── routes.md                 # Phase 1 — routes new, changed and asserted-unchanged
├── checklists/
│   └── requirements.md           # Spec quality checklist (all items pass)
└── tasks.md                      # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── models.py                     # + McMasterOrderLine, McMasterOrder (frozen dataclasses,
│                                 #   from_payload, the pack->unit arithmetic)
│                                 #   OrderLineState and ReviewedLine reused unchanged
├── database.py                   # ~ Purchase.digikey_line_number -> order_line_number
├── catalog_service.py            # + review_mcmaster_order, capture_mcmaster_order,
│                                 #   find_mcmaster_order_lines, find_mcmaster_receivable
│                                 # ~ resolve_scan: one branch in FREE_TEXT, before the
│                                 #   vendor-scoped identifier lookup
│                                 # ~ the column rename's call sites
├── product/
│   └── routes.py                 # + mcmaster_order_confirm, mcmaster_order_detail,
│                                 #   purchase_receive_choice, _mcmaster_part_from_url
│                                 # ~ api_capture: branch on the `order` payload
│                                 # ~ _receive_url: read the purchases, not the ECIA fields
├── static/js/
│   └── capture-agent.js          # + page dispatch; + the McMaster order and product readers.
│                                 #   The Amazon section is not edited.
└── templates/product/
    ├── mcmaster_order_review.html    # + the review (FR-003..FR-009, FR-020a)
    ├── mcmaster_order.html           # + a captured order (FR-027..FR-031)
    └── receive_choice.html           # + the candidate chooser (FR-032a)

migrations/versions/
└── <rev>_rename_digikey_line_number.py   # + reversible column rename

tests/
├── unit/
│   ├── test_mcmaster_payload.py  # + parsing, pack arithmetic, malformed payloads
│   ├── test_mcmaster_capture.py  # + review states, the write, re-capture reconciliation
│   ├── test_mcmaster_receive.py  # + the three FR-032 scan cases
│   └── test_digikey_capture.py   # ~ the column rename
└── e2e/
    ├── fixtures/
    │   ├── mcmaster_order.html   # + saved, scrubbed (PREREQUISITE — research.md §5)
    │   └── mcmaster_product.html # + saved
    ├── test_mcmaster_order.py    # + bookmarklet -> review -> confirm -> order screen
    ├── test_mcmaster_product.py  # + bookmarklet -> confirmation -> product
    └── test_mcmaster_receive.py  # + scan receives; two candidates offer a choice
```

**Structure Decision**: the existing four-layer Flask layout is kept exactly as it is
(Constitution II) — domain dataclasses in `app/models.py`, ORM in `app/database.py`, business
logic in `app/catalog_service.py`, thin routes in `app/product/routes.py`. Nothing new is
introduced above or beside it. The e2e tests reuse the harness in
`tests/e2e/test_product_page_capture.py`, which already clicks the **real** bookmarklet against
a fixture served from the application's own origin.

## Complexity Tracking

> No Constitution Check violations. Nothing to justify.

Three judgement calls are recorded in research.md rather than here, because each of them chose
the *simpler* option and the reasoning is worth keeping:

| Call | Chosen | Rejected |
|---|---|---|
| Vendor orchestration (§7) | McMaster gets its own service methods; the DigiKey path is not refactored | A shared vendor-neutral capture core — the abstraction Principle I warns about, built by editing the application's most intricate write path, for a saving of ~150 lines |
| Line identity (§8) | Rename one column, both vendors write it | A second nullable column meaning the same thing |
| Order transport (§2) | One extra form field on the endpoint the bookmarklet already names | A second endpoint or a second bookmarklet — both force the operator to re-drag it |
