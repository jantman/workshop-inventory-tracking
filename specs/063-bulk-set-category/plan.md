# Implementation Plan: Bulk Set Category

**Branch**: `robot-army/issue-201-add-support-for-bulk-category-setting` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/063-bulk-set-category/spec.md`

## Summary

Add a **Set Category** button to each of the three pages that already have row selection:
Products, an order's page, and Outstanding Products. It sits next to Print Labels. It opens a
small shared dialog with one category input that offers existing categories as suggestions.
Confirming sends one JSON request, `POST /api/products/category`, with the distinct product
ids behind the ticked rows and the entered category. A new service method,
`CatalogService.set_category(product_ids, category_path)`, validates the category with the
same `_validate_category_path` that Edit Product uses. It refuses a blank category, checks that
every id exists, and writes all of them in one session, so the update is all-or-nothing.

On success the page script unticks every box and reloads. The route has already flashed
"Set category … on N products", so the reloaded page shows that message, an empty selection,
and on Products the new categories under the same filters, because the reload keeps the query
string. On failure the dialog stays open and shows the error, and the selection is untouched
(FR-011).

The dialog markup is a Jinja macro (`_bulk_category_modal.html`), and its behavior is one
class (`BulkSetCategoryDialog` in `bulk-set-category.js`). This follows the pattern of
`_bulk_label_modal.html` and `BulkLabelPrintDialog`. The two existing selection scripts,
`product-list-labels.js` and `order-bulk-actions.js`, arm the new button and pass the dialog
their selection, just as they do for labels. The order page and Outstanding Products share
`_order_bulk_toolbar.html`, so the button is added once for both.

## Technical Context

**Language/Version**: Python 3.13 (Flask), vanilla JavaScript

**Primary Dependencies**: Flask, SQLAlchemy, Bootstrap 5. Nothing new.

**Storage**: MariaDB, existing `products.category_path`. No schema change.

**Testing**: pytest unit tests via `nox -s tests`; Playwright e2e via `nox -s e2e`

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals / Constraints / Scale**: N/A. A selection is at most a few hundred rows.
There is one `IN` query and one commit.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ One service method, one endpoint, one dialog macro, one small JS class, reused by all three pages. No new dependency. Suggestions come from the existing `/api/categories` through the existing `datalist.js`. No DOM patching after a save: a reload shows the truth. |
| **II. Layered Architecture** | ✅ Validation and the write live in `CatalogService`. The route only parses JSON, calls the service, flashes and returns JSON. |
| **III. Exact Numerics** | ✅ N/A. No measurements. |
| **IV. Test Discipline** | ✅ Unit tests cover the service (normalization parity with `update_product`, blank refused, over-length refused, missing id leaves all unchanged, duplicate ids, nothing but the category changes) and the route (status codes, flash). The e2e tests cover each of the three pages: set, verify, selection cleared, plus the failure path keeping the selection. They wait with `expect` on rendered state after the reload and seed with `add_test_data`. Screenshots that show the changed toolbars are regenerated via `nox -s screenshots`. |
| **V. MariaDB Source of Truth** | ✅ No schema change. One transaction per update. |
| **VI. Item Lifecycle Invariants** | ✅ N/A. These are products, not JA-ID items. |
| **Threat model** | ✅ Ids are checked to exist so that a stale page fails cleanly, for correctness. The request uses `csrfFetch` like the label endpoint. No hardening added. |

**Post-design re-check**: ✅ Unchanged after Phase 1. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/063-bulk-set-category/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── set-category.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                          # set_category (new)
├── product/routes.py                           # api_set_product_category (new)
├── static/js/bulk-set-category.js              # BulkSetCategoryDialog (new)
├── static/js/catalog-suggestions.js            # also fills #bulk-category-suggestions
├── static/js/product-list-labels.js            # arm button, open dialog
├── static/js/order-bulk-actions.js             # arm button, open dialog
├── templates/_bulk_category_modal.html         # dialog macro (new)
├── templates/product/_order_bulk_toolbar.html  # Set Category button
├── templates/product/search.html               # Set Category button, modal, scripts
├── templates/product/order.html                # modal, scripts
└── templates/product/outstanding.html          # modal, scripts

tests/
├── unit/test_bulk_set_category.py              # new
└── e2e/test_bulk_set_category.py               # new
docs/user-manual.md                             # short "Setting a category on several products" section
```

**Structure Decision**: Existing single Flask app layout. One new macro, one new JS file, two
new test files.

## Complexity Tracking

No violations.
