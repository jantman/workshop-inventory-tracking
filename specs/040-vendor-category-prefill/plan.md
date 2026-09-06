# Implementation Plan: A Vendor's Category Is Not the Shop's Category

**Branch**: `robot-army/issue-138-a-digikey-order-capture-pre-fills-the` | **Date**: 2026-09-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/040-vendor-category-prefill/spec.md`

## Summary

A DigiKey capture writes DigiKey's own catalog name — "Power Supplies - Board Mount" — into the
product's `category_path`. That field is free-form and the browsable tree on `/products/categories`
is built from the distinct values in use, so a vendor category left unchanged once becomes a
permanent branch of the shop's taxonomy. Issue #138's Option 1 is adopted: the vendor's category
stops being a source for the field.

Four code sites carry it toward a product, and one page promises it:

1. **`CatalogService._create_digikey_product`** (`app/catalog_service.py`) passes
   `part.category_path` into the new `Product`. Removed; the field is simply not set, which leaves
   it `None` — the same state a product created by any other capture path arrives in.
2. **`CatalogService._enrich_digikey_product`** fills a blank `category_path` from the part detail.
   The category clause is removed; the manufacturer and specification clauses stay exactly as they
   are, and the fill-gaps-only rule they follow is unchanged.
3. **`app/templates/product/digikey_part_review.html`** carries `part.category_path` in a hidden
   input posted to `product_new`. The hidden input is removed and a visible, empty Category field
   takes its place next to the Storage Location and Sub-Location inputs the page already has, so
   the page can still file a product — with the operator's vocabulary, not DigiKey's. DigiKey's
   category stays in the "What DigiKey says" detail list, where it is information.
4. **`product_new`'s scan-prefill branch** (`app/product/routes.py`) copies `part.category_path`
   into the `prefill` mapping that fills the Add Product form, so a scanned bag opens with the
   visible Category input already carrying DigiKey's value. The one key is dropped from that
   `prefill.update(...)`; every other pre-loaded value stays. This site is not named in the issue
   and was found while planning — see [research.md](./research.md).
5. **`app/templates/product/order_review.html`**'s unenriched-lines warning tells the operator that
   thin lines "arrive without a manufacturer, category or specifications". After this change no
   line arrives with a category, so the sentence is corrected rather than left stating something
   the capture no longer does.

No service signature changes, no route signature changes, no schema change, no Alembic revision, no
JavaScript. The category field, the taxonomy, the tree and the rename tooling are all untouched —
this feature removes a writer, not a capability.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x, Jinja2, Bootstrap 5.3.2.
No new dependency; no new JavaScript.

**Storage**: MariaDB via SQLAlchemy in production, SQLite through the same `Storage` interface in
unit tests. **Unchanged.** No table, column, index or constraint is touched; `Product.category_path`
keeps its type, length and nullability. There is no migration, and deliberately no data cleanup of
categories already recorded (spec FR-008).

**Testing**: `nox -s tests` (pytest, network blocked) and `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`). Three existing unit assertions currently assert the defect and
must be inverted (`tests/unit/test_digikey_capture.py`, `tests/unit/test_order_enrichment.py`);
new unit tests cover all three write sites, and one E2E test covers the single-part page's visible
Category field.

**Target Platform**: Server-rendered Flask app on a home LAN, single operator.

**Project Type**: Web application, server-rendered. No frontend framework and no build step.

**Performance Goals**: None. The change removes work rather than adding any.

**Constraints**: Capture must keep succeeding with no new question, warning or validation when a
category is absent (spec FR-006). Nothing already recorded may change (FR-008).

**Scale/Scope**: Two clauses removed from one service module, one key removed from one route's
prefill mapping, one hidden input swapped for one visible field in one template, one sentence of
on-page copy, three passages of the user manual. Under 30 lines of application code; the test and
documentation surface is larger than the change.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — see below.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS, and the principle is the argument.** Option 1 deletes code; Options 2 and 3 add a review control and a mapping table respectively for a problem one deletion solves. No abstraction, no configuration knob, no "vendor category policy" seam. FR-009 ("the rule holds for every vendor") is satisfied by there being no code that reads a vendor category into the field — not by a vendor-neutral mechanism enforcing it. |
| **II. Layered Architecture Boundaries** | **PASS.** Both service edits are inside `app/catalog_service.py`, the services layer where the business rule belongs. The template edits are presentation only. No route gains logic, no ORM query moves, no new layer. |
| **III. Exact Numerics** | **N/A.** No measured quantity is involved. |
| **IV. Test Discipline Through Nox** | **PASS, with an obligation.** This changes behavior, so tests land with it (`nox -s tests` and `nox -s e2e` both green before merge). Three existing tests assert the old behavior and are inverted rather than deleted — the assertion is the record of the decision, so it is rewritten to record the new one. Any new E2E test waits on observable state; the single-part page test asserts on the Category input's value and on the created product's rendered category, both of which are ordinary `expect()` conditions. No fixed wait is added. |
| **V. MariaDB Is the Source of Truth** | **PASS.** No schema change, therefore no Alembic revision. FR-008 explicitly declines a data migration; there is nothing to make reversible. |
| **VI. Item Lifecycle and History Invariants** | **N/A.** Products and their categories are not inventory items; no JA ID, active-row or shortening-history path is touched. |

**Verdict: no violations, and no entry needed in Complexity Tracking.** Re-checked after Phase 1:
the design added one visible form field reusing an existing input contract and no new module,
abstraction, dependency or table, so every row above stands unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/040-vendor-category-prefill/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── digikey-part-capture-form.md   # The single-part capture page's form contract
├── checklists/
│   └── requirements.md
├── spec.md
└── tasks.md             # /speckit-tasks output
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                      # _create_digikey_product, _enrich_digikey_product
├── product/routes.py                       # product_new's scan-prefill branch
└── templates/product/
    ├── digikey_part_review.html            # hidden category_path → visible empty Category field
    └── order_review.html                   # unenriched-lines warning copy

tests/
├── unit/
│   ├── test_digikey_capture.py             # invert the "category is not None" assertion
│   ├── test_order_enrichment.py            # invert "a blank category is filled"
│   └── test_product_routes.py              # single-part form fields; scan prefill
└── e2e/
    └── test_digikey_part.py                # the visible, empty Category field on that page

docs/
└── user-manual.md                          # three passages promising DigiKey's category
```

**Structure Decision**: The existing layout is used unchanged. This feature adds no module and no
directory; every edit lands in a file that already exists.

## Phase 0: Research

See [research.md](./research.md). Three questions were open and all three are resolved there:
which sites carry the value (four, not the one the issue names), whether removing the hidden field
strands the single-part capture page (it does, hence FR-004), and whether anything downstream
depends on a captured product having a non-empty category (nothing does).

## Phase 1: Design

- [data-model.md](./data-model.md) — what `Product.category_path` is, what the tree is derived
  from, and why "no schema change" is the whole data story.
- [contracts/digikey-part-capture-form.md](./contracts/digikey-part-capture-form.md) — the fields
  the single-part capture page posts to `product_new`, before and after.
- [quickstart.md](./quickstart.md) — how to prove the three doors are shut, by test and by hand.

## Complexity Tracking

No Constitution Check violations. This table is intentionally empty.
