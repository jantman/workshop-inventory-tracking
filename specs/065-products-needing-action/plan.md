# Implementation Plan: Products Needing Action

**Branch**: `robot-army/issue-209-products-needing-action-page` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/065-products-needing-action/spec.md`

## Summary

Add a `missing` filter to the product list (`/products`) with values `category`,
`location` and `either`, implemented in `CatalogService.search_products()` next to the
existing `stock` filter and exposed as a "Missing" `<select>` in the filter form. Add a
**Products → Needs Action** menu entry linking to `/products?missing=either`. Setting the
missing data uses existing tools (bulk Set Category on the same list, product edit, Move
Products).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1, SQLAlchemy 2.0 (legacy `Query` API), Jinja2, Bootstrap 5.3

**Storage**: MariaDB (SQLite in unit tests). No schema change.

**Testing**: pytest via `nox -s tests` and `nox -s e2e` (Playwright)

**Target Platform**: Linux server, LAN-only web app

**Project Type**: Server-rendered web application

**Performance Goals**: None beyond current list behavior (existing 500-row limit applies)

**Constraints**: None new

**Scale/Scope**: One service method, two routes (page and JSON API), one template, the navbar, user manual

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ One new keyword argument on an existing method, one `<select>`, one menu link. No new page: "Needs Action" is a link to a filtered view of the existing list, which is exactly what the issue asks for. |
| **II. Layered Architecture** | ✅ The query lives in `CatalogService`; routes only pass the request argument through. |
| **III. Exact Numerics** | ✅ N/A. |
| **IV. Test Discipline** | ✅ Unit tests for each filter value, blank-string handling, combination with another filter, and the unknown-value error. E2E: the form drives the filter and keeps it selected; the menu link lands on the filtered list. E2E seeds via `live_server.add_test_data`-style direct seeding where possible and waits with `expect()`, no fixed waits. |
| **V. MariaDB Source of Truth** | ✅ No schema change, no migration. |
| **VI. Item Lifecycle Invariants** | ✅ N/A — products, not inventory items. |
| **Threat model** | ✅ N/A. Unknown filter values are rejected for correctness, like `stock`. |
| **Screenshots** | `app/templates/**` changes: the product list filter bar gains a field, so `user-manual/product_search.png` is regenerated. The navbar dropdown is closed in every shot, so no other shot should change; baseline churn is measured and discarded. |

**Post-design re-check**: ✅ Unchanged after Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/065-products-needing-action/
├── plan.md
├── research.md
├── quickstart.md
├── contracts/
│   └── missing-filter.md
└── tasks.md
```

No `data-model.md`: the feature reads two existing nullable columns
(`products.category_path`, `products.location`) and adds no data.

### Source Code (repository root)

```text
app/catalog_service.py             # search_products(missing=...), _apply_missing_filter
app/product/routes.py              # pass ?missing= through on /products and /api/products/search
app/templates/product/search.html  # "Missing" select in the filter form
app/templates/base.html            # Products -> Needs Action
docs/user-manual.md                # Finding Products: the filter and the menu entry
docs/images/screenshots/user-manual/product_search.png

tests/unit/test_product_search.py  # TestMissingFilter
tests/unit/test_product_routes.py  # page/API pass-through (if not covered by e2e)
tests/e2e/test_product_search.py   # form drives filter; Needs Action menu link
```

**Structure Decision**: Existing files only.

## Complexity Tracking

No violations.
