# Implementation Plan: Products Table Location Columns and Width

**Branch**: `robot-army/issue-212-products-needs-action-improvements` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/066-products-table-location-width/spec.md`

## Summary

The product list (`/products`, every view of it) gets separate **Location** and
**Sub-location** columns in place of the single Location cell that tacked the
sub-location on in muted text, and the page drops Bootstrap's fixed-width
`.container` (max 1320px, ~1294px of content at 1920px) for a full-width
`.container-fluid` so the extra column fits and nothing is pushed off-screen into the
table's horizontal scroll. The change is two templates; no service, route, data or
JavaScript changes.

## Technical Context

**Language/Version**: Python 3.13, Jinja2 templates, Bootstrap 5 (already loaded)

**Primary Dependencies**: Flask; nothing new

**Storage**: N/A — reads existing `products.location` / `products.sub_location`

**Testing**: `nox -s tests` (unit, Flask test client) and `nox -s e2e` (Playwright)

**Target Platform**: Desktop browser, 1920×915 primary; tablet/phone must stay usable

**Project Type**: Web application (server-rendered)

**Performance Goals**: N/A

**Constraints**: Width change confined to the product list page (FR-009)

**Scale/Scope**: One page, one table

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ One `{% block %}` in `base.html` around the `<main>` container class, overridden by the product list only; one extra `<th>`/`<td>`. No new CSS framework, no per-device layout code, no column configuration. |
| **II. Layered Architecture** | ✅ Template-only; routes and services untouched. |
| **III. Exact Numerics** | ✅ N/A. |
| **IV. Test Discipline** | ✅ Unit test (test client) asserts the headers and per-row cells, including blank cells and the empty-row `colspan`. E2E at 1920×915 asserts the table width and that the Sub-location header is in view without horizontal scroll, waiting with `expect()` only; seeds via `live_server.add_test_data`-style direct seeding. |
| **V. MariaDB Source of Truth** | ✅ No schema change, no migration. |
| **VI. Item Lifecycle Invariants** | ✅ N/A — products, not inventory items. |
| **Threat model** | ✅ N/A. |
| **Screenshots** | `app/templates/**` changes: `user-manual/product_search.png` shows the new columns and width and is regenerated. Other screenshots should not change (the block default keeps `container`); baseline churn is measured and discarded. |

**Post-design re-check**: ✅ Unchanged after Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/066-products-table-location-width/
├── plan.md
├── research.md
├── quickstart.md
├── contracts/
│   └── product-table.md
└── tasks.md
```

No `data-model.md`: the feature displays two existing nullable columns and adds no data.

### Source Code (repository root)

```text
app/templates/base.html            # {% block main_container_class %}container{% endblock %} on <main>
app/templates/product/search.html  # container-fluid override; Location + Sub-location columns; colspan 7
docs/user-manual.md                # Finding Products: mention the columns (if the section lists them)
docs/images/screenshots/user-manual/product_search.png

tests/unit/test_product_routes.py  # columns rendered on /products and /products?missing=either
tests/e2e/test_product_table_layout.py  # 1920x915: table width and columns in view; 768/390: no page overflow
```

**Structure Decision**: Existing files only.

## Complexity Tracking

No violations.
