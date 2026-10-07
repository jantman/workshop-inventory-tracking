# Implementation Plan: Edit Purchases and Orders

**Branch**: `robot-army/issue-192-product-purchases-allow-editing` | **Date**: 2026-10-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/061-edit-purchases-orders/spec.md`

## Summary

Two server-rendered edit screens, each a GET/POST route shaped like the existing receive and
delete screens:

1. **Edit Purchase** — `GET/POST /purchases/<id>/edit?return_to=order|product`. Every stored
   field of one purchase that capture can get wrong, pre-filled. The route calls a new
   `CatalogService.update_purchase(purchase_id, **fields)`, which validates everything before
   touching the row (reusing `_validate_purchase_quantity`, `_validate_price`,
   `_validate_pack_size`, `_validate_receipt_order`, `_parse_datetime`, `_clean`) and never
   touches the product. Changing the vendor or supplier order number moves the purchase between
   orders, which is how a hand-recorded purchase is re-attached to its order (US2).
2. **Edit Order** — `GET/POST /products/orders/<vendor>/<order_number>/edit`. Order number,
   order date and customer reference, applied to every line of the order in one session by a
   new `CatalogService.update_order(...)`. A rename onto another existing order is refused —
   this screen never merges orders.

Entry points: a pencil button beside the existing trash button on the product page's purchase
history and on every order line, and an "Edit Order" page action on the order page.

## Technical Context

**Language/Version**: Python 3.13 (Flask), Jinja2 templates

**Primary Dependencies**: Flask, SQLAlchemy, Bootstrap 5. Nothing new.

**Storage**: MariaDB, existing `purchases` table. No schema change.

**Testing**: pytest unit tests via `nox -s tests`; Playwright e2e via `nox -s e2e`

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals / Constraints / Scale**: N/A — one purchase, or an order of a handful of lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ Two plain forms, two service methods, no JS. Reuses every existing validator. No generic "edit any field" machinery; the fields are listed. No new dependencies. |
| **II. Layered Architecture** | ✅ Validation and writes in `CatalogService`; routes read the form, call the service, flash and redirect. Route-side work is limited to choosing a redirect and summarising already-loaded lines for pre-fill. |
| **III. Exact Numerics** | ✅ Prices go through `_validate_price` (Decimal, rounded to the cent, floats refused). Quantities are integers. |
| **IV. Test Discipline** | ✅ Unit tests for both service methods (validation, no stock effects, all-or-nothing, conflicts) and routes; e2e tests for each entry point with seeded data and `expect()` waits only. No screenshot-config page changes. |
| **V. MariaDB Source of Truth** | ✅ No schema change; edits are single transactions. |
| **VI. Item Lifecycle Invariants** | ✅ N/A — purchases, not JA-ID items. |
| **Data integrity** | ✅ Stock counts are never altered by an edit (same reasoning as 032 delete). Order rename refuses to merge into another order. Order line uniqueness within an order is enforced on change. Time-of-day of stored dates is preserved when the edited date is the same day. |
| **Threat model** | ✅ `return_to` is a two-value flag, never a URL (as in 032). CSRF token on both forms. |

**Post-design re-check**: ✅ Unchanged after Phase 1. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/061-edit-purchases-orders/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── edit-routes.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                     # update_purchase, update_order (new)
├── product/routes.py                      # purchase_edit, order_edit (new routes)
├── templates/product/purchase_edit.html   # new
├── templates/product/order_edit.html      # new
├── templates/product/detail.html          # Edit button in purchase history
└── templates/product/order.html           # Edit button per line, Edit Order action

tests/
├── unit/test_purchase_edit.py             # new
└── e2e/test_purchase_edit.py              # new
docs/user-manual.md                        # "Correcting a Purchase or an Order"
```

**Structure Decision**: Existing single Flask app layout; two templates and two test files added.

## Complexity Tracking

No violations.
