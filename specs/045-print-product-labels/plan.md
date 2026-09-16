# Implementation Plan: Print labels for selected products from the All Products view

**Branch**: `robot-army/issue-157-print-labels-from-all-products-view` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/045-print-product-labels/spec.md`

## Summary

Give `/products` the same check-rows-and-print-labels behaviour `/inventory` already has, with
**no backend change at all**.

Everything the server side needs already exists and is already correct: `POST
/api/products/<id>/label` composes and prints one product's label with a 1–99 copy count, and
`GET /api/labels/types` lists the six label stocks. A bulk run is N calls to the first endpoint —
exactly how the inventory list already works against its own per-item endpoint. So this feature is
entirely template and JavaScript.

The reuse the issue asks for is taken at the one place it is worth taking: the ~230 lines of
bulk-print dialog orchestration (load stocks, enable on choice, validate the count once before
anything prints, loop with progress, tally, report failures by name, reset on close) currently live
inside `inventory-list.js` and are generic apart from four parameters. They move to a shared
`BulkLabelPrintDialog`, and the dialog markup moves to a shared Jinja macro. The inventory list then
*uses* what it used to *contain*, with its element ids and its exact user-visible strings preserved,
and the products list becomes a small file: read checkboxes, hand the dialog a list, post to the
product label endpoint.

Net effect: one moved block, two new small files, one table gains a column and a button. No new
route, no new service, no new dependency, no migration.

## Technical Context

**Language/Version**: Python 3.13; browser JavaScript (ES2020, no build step)

**Primary Dependencies**: Flask 3.1.x, Jinja2, Bootstrap 5.3.2. **No new dependencies.**

**Storage**: MariaDB via SQLAlchemy — **not touched**. No schema change, no Alembic revision.

**Testing**: `nox -s tests` (pytest, SQLite, network blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`)

**Target Platform**: Flask app on a home LAN, server-rendered HTML

**Project Type**: Server-rendered web application (single project)

**Performance Goals**: None. A print run is one person pressing one button; the run is serialized
per product exactly as the inventory list's already is, so the operator sees progress advance.

**Constraints**: The six label stocks and the 1–99 copy count must stay in agreement across all
print dialogs — which they do by construction, because all of them read `GET /api/labels/types` and
`window.readLabelCount`. Existing inventory-list behaviour must be byte-identical in its
user-visible strings (its E2E suite asserts them).

**Scale/Scope**: 2 new files, 4 modified files, 1 new E2E test module, 3 one-word selector fixes in
existing E2E tests, plus regenerated screenshots.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — see bottom.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS.** No new endpoint, service, table, or dependency. The one abstraction introduced (`BulkLabelPrintDialog`) has **two** real call sites on the day it lands, which is the condition the principle sets — it is an extraction of working code, not speculative generality. It carries no options beyond the four things that genuinely differ. Deliberately *not* done: converting the other three inline print dialogs, adopting the `InventoryTable` component for a server-rendered table, adding a batch print endpoint, or persisting selection. |
| **II. Layered Architecture Boundaries** | **PASS, trivially.** No route, service, storage, or model file is edited. The feature is templates plus static JS. |
| **III. Exact Numerics** | **PASS.** No measurement arithmetic. The per-unit price on a product label is already formatted server-side from `Decimal` by `app/services/product_label.py`; this feature does not touch label composition. |
| **IV. Test Discipline Through Nox** | **PASS.** Run via nox. New E2E tests wait on observable state only — the conditions are enumerated in [quickstart.md](./quickstart.md) so no author has to guess. No new pytest marker. Behaviour changes land with tests. |
| **V. MariaDB Is the Source of Truth** | **PASS.** No schema change, so no Alembic revision — and therefore nothing to make reversible. |
| **VI. Item Lifecycle and History Invariants** | **PASS.** Products are catalog records, not inventory items; no JA ID, active-row, or history path is touched. |
| **Operating Context / Threat Model** | **PASS.** No auth, no sanitization layer. The product label endpoint is already CSRF-protected and `csrf.js` is loaded globally from `base.html`, so the new caller uses `csrfFetch` like every other catalog AJAX call. |
| **Workflow: screenshots** | **Obligation, not a violation.** `app/templates/**` and `app/static/js/**` change, so `nox -s screenshots_headless` must run and the products-list screenshot must be committed. |
| **Workflow: branch + PR** | Satisfied — work is on the feature branch and ships as a PR. |

**No entries in Complexity Tracking.** No gate is violated.

## Project Structure

### Documentation (this feature)

```text
specs/045-print-product-labels/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── bulk-label-print.md
├── checklists/
│   └── requirements.md
├── spec.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── templates/
│   ├── _bulk_label_modal.html        # NEW — Jinja macro for the bulk print dialog
│   ├── inventory/
│   │   └── list.html                 # MODIFIED — inline dialog replaced by the macro call
│   └── product/
│       └── search.html               # MODIFIED — checkbox column, select-all, Print Labels
│                                     #            action, macro call, script tags
└── static/js/
    ├── bulk-label-print.js           # NEW — shared BulkLabelPrintDialog
    ├── inventory-list.js             # MODIFIED — delegates to BulkLabelPrintDialog
    ├── product-list-labels.js        # NEW — products selection + printOne
    └── label-count.js                # UNCHANGED — already the shared count reader

tests/
├── e2e/
│   ├── test_bulk_label_printing_products.py   # NEW
│   ├── test_bulk_label_printing_list.py       # UNCHANGED — the refactor's regression net
│   ├── test_product_search.py                 # MODIFIED — 2 column-position selectors
│   └── test_product_specifications.py         # MODIFIED — 1 column-position selector
└── unit/
    └── test_product_routes.py                 # MODIFIED — products page renders the controls

docs/images/screenshots/              # REGENERATED (products list gains a column + button)
```

**Structure Decision**: The existing single-project layout is used as-is. No backend file
(`app/product/routes.py`, `app/main/routes.py`, `app/services/*`) is edited, which is the plan's
most important structural property: the endpoints, the label composition, and the 1–99 validation
are consumed exactly as they stand.

## Key Design Decisions

Full reasoning, including what was rejected, is in [research.md](./research.md). In brief:

1. **No batch endpoint.** N client-side POSTs to the existing per-product endpoint. This is what
   satisfies FR-010 (progress naming which product of how many) and FR-011 (one failure does not
   abort the run) for free, and it is precisely how the inventory list works.
2. **Extract the dialog, don't copy it.** `BulkLabelPrintDialog` takes `{modalId, prefix, noun,
   nounPlural, printOne}`. Everything else is identical between the two pages.
3. **Extract the markup too.** A Jinja macro guarantees the element ids the shared JS reads actually
   exist on both pages, which a copy-pasted block does not.
4. **Plain DOM checkboxes on the products table**, not the `InventoryTable` component — that
   component renders its own tbody from `/api/inventory/list` and keys on `ja_id`. The products
   table is server-rendered Jinja; adopting the component would mean rewriting the page.
5. **Only two of the five print dialogs are touched.** The dialogs on `inventory/add.html`,
   `inventory/search.html`, and `product/detail.html` are out of scope (FR-014).
6. **Checkbox column goes first**, matching the inventory table. Three existing E2E selectors say
   `td:first-child a`; they become `td a`, which is the form the other twenty-odd call sites in the
   suite already use.

## Post-Design Constitution Re-Check

Re-evaluated against the Phase 1 artifacts:

- **Simplicity** — the design got *smaller* during Phase 1, not larger: the batch-endpoint option
  was dropped, so the backend diff is empty. The shared dialog's parameter list is four entries and
  was not allowed to grow to cover the three out-of-scope dialogs.
- **Layering** — unchanged and unthreatened; there is no server-side code in this feature.
- **Data integrity** — nothing writes to the database. The worst outcome of a bug here is a label
  that does or does not come out of a printer, which is recoverable by pressing the button again.
- **Testing** — `quickstart.md` names the observable condition for every wait in the new E2E module,
  so the suite gains no fixed-duration wait.

**Result: all gates still pass. Complexity Tracking remains empty.**

## Complexity Tracking

No constitutional violation requires justification.
