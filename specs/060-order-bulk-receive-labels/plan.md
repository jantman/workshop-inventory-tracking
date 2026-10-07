# Implementation Plan: Bulk Receive and Bulk Label Printing on the Order Page

**Branch**: `robot-army/issue-194-order-page-bulk-receive-and-bulk-label` | **Date**: 2026-10-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/060-order-bulk-receive-labels/spec.md`

## Summary

The order page (`product/order.html`, one template for every vendor) gains a checkbox per
line that has a product, a header select-all checkbox, and a toolbar with two actions:

1. **Print Labels** opens the shared `BulkLabelPrintDialog` (`bulk-label-print.js` +
   `_bulk_label_modal.html`), posting to the existing `/api/products/<id>/label` endpoint —
   the same wiring the products list uses. The selection is deduplicated by product.
2. **Receive** submits a plain HTML form (`POST /products/orders/<vendor>/<order_number>/receive`)
   carrying the ticked lines' purchase ids and one received date (blank means today). The
   route calls a new service method, `CatalogService.receive_order_lines(...)`, which
   receives every ticked outstanding line in **one session** — so a refusal rolls back all
   of them — and redirects back to the order page with a flash stating received / skipped.

The receipt's effects (set received date, raise a tracked count, clear a manual flag) are
extracted from `receive_purchase` into one private helper, `_apply_receipt`, called by both
paths, so bulk and single receipt cannot diverge (SC-003).

## Technical Context

**Language/Version**: Python 3.13 (Flask), vanilla JavaScript

**Primary Dependencies**: Flask, SQLAlchemy, Bootstrap 5. Nothing new.

**Storage**: MariaDB, existing `purchases` and `products` tables. No schema change.

**Testing**: pytest unit tests via `nox -s tests`; Playwright e2e via `nox -s e2e`

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals / Constraints / Scale**: N/A — an order has a handful of lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ Reuses the shared label dialog and the existing label endpoint unchanged. Receive is a plain form post with no JS beyond enabling buttons. One new service method; one extracted helper replaces logic that would otherwise be duplicated. No new dependencies. |
| **II. Layered Architecture** | ✅ All receiving logic in `CatalogService`; the route only reads the form, calls the service, flashes and redirects. |
| **III. Exact Numerics** | ✅ Quantities are the stored integer purchase quantities; no arithmetic on measurements is introduced. |
| **IV. Test Discipline** | ✅ Unit tests for the service (effects parity with single receipt, skip, all-or-nothing, wrong-order ids) and the route; e2e for both actions, waiting on rendered state via `expect`, data seeded directly. The order page is not in `screenshot_config.yaml`, so no screenshot regenerates. |
| **V. MariaDB Source of Truth** | ✅ No schema change. Bulk receipt is one transaction. |
| **VI. Item Lifecycle Invariants** | ✅ N/A — purchases and products, not JA-ID items. |
| **Threat model** | ✅ Posted ids are checked against the order for correctness (a stale or wrong id must not receive another order's line), not as a defense. CSRF token included as on every form. |

**Post-design re-check**: ✅ Unchanged after Phase 1. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/060-order-bulk-receive-labels/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── order-bulk-actions.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                 # _apply_receipt (extracted), receive_order_lines (new)
├── product/routes.py                  # order_receive_lines (new POST route)
├── templates/product/order.html       # checkboxes, toolbar, receive form, label modal
└── static/js/order-bulk-actions.js    # selection state + label dialog wiring (new)

tests/
├── unit/test_order_bulk_receive.py    # new
└── e2e/test_order_bulk_actions.py     # new
docs/user-manual.md                    # order page section: the two bulk actions
```

**Structure Decision**: Existing single Flask app layout; one new JS file and two new test
files.

## Complexity Tracking

No violations.
