# Tasks: Products Table Location Columns and Width

**Input**: Design documents from `specs/066-products-table-location-width/`

**Prerequisites**: plan.md, spec.md, research.md, contracts/product-table.md, quickstart.md

**Tests**: Included — Constitution IV requires them; unit tests through the Flask test client, e2e through Playwright.

## Phase 1: Setup

No setup: existing files only, no dependencies.

## Phase 2: Foundational

No blocking prerequisites; the two stories touch different parts of the templates.

## Phase 3: User Story 1 — Location and Sub-location columns (P1) 🎯 MVP

**Goal**: Every view of `/products` shows separate Location and Sub-location columns.

**Independent Test**: `/products` and `/products?missing=either` render the headers in contract order and each product's location and sub-location in their own cells, blank when unset.

- [X] T001 [US1] Add `TestTheProductsListShowsWhereEachProductIs` to tests/unit/test_product_routes.py: headers in contract order; a product with location + sub-location shows each in `td.product-location` / `td.product-sub-location`; a product with neither shows both cells empty; same on `?missing=either`; update `test_the_empty_row_spans_every_column` to expect `colspan="7"`
- [X] T002 [US1] In app/templates/product/search.html replace the combined Location cell with `<td class="product-location">` and `<td class="product-sub-location">` under `Location` / `Sub-location` headers, and set the empty-row `colspan` to 7
- [X] T003 [US1] Run `nox -s tests` and confirm T001 passes

## Phase 4: User Story 2 — Full-width product list (P2)

**Goal**: At 1920×915 the product table is ≥1800px wide and every column is in view; other pages unchanged; small screens still usable.

**Independent Test**: Playwright at 1920×915 measures `#product-table` width ≥ 1800 and `.table-responsive` `scrollWidth <= clientWidth` with long seeded descriptions and tags; at 390px the document does not scroll horizontally.

- [X] T004 [US2] In app/templates/base.html wrap the `<main>` container class in `{% block main_container_class %}container{% endblock %}`
- [X] T005 [US2] In app/templates/product/search.html override `main_container_class` with `container-fluid`
- [X] T006 [US2] Add a unit assertion in tests/unit/test_product_routes.py that `/products` renders `<main class="container-fluid` and another page (e.g. `/products/categories`) still renders `<main class="container `
- [X] T007 [US2] Add e2e tests in a new tests/e2e/test_product_table_layout.py (seeded through `CatalogService`, like test_products_needing_action.py): at 1920×915 with a product carrying a long description, several tags, a location and a sub-location, `expect` the row to render, then assert table width ≥ 1800px, the Sub-location header is in the viewport, and the table wrapper does not overflow horizontally; at 390×844 assert the document does not overflow horizontally
- [X] T008 [US2] Run `nox -s e2e -- tests/e2e/test_product_table_layout.py` plus the other product-list e2e files (detached) and confirm T007 passes

## Phase 5: Polish

- [X] T009 [P] Update the "Finding Products" section of docs/user-manual.md if it describes the list's columns
- [X] T010 Regenerate `docs/images/screenshots/user-manual/product_search.png` via the screenshots nox session; commit only that shot, discarding unrelated baseline churn
- [X] T011 Run full `nox -s tests` and full `nox -s e2e` (detached, ≥20 min budget); confirm the working tree is clean afterwards apart from intended changes
- [X] T012 Spelling check: `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing

## Dependencies

- US1 (T001–T003) and US2 (T004–T008) are independent; both edit search.html, so do them sequentially.
- Polish depends on both stories.

## Parallel Opportunities

- T009 alongside T010.

## Implementation Strategy

MVP is US1 (the columns are what make Needs Action legible); US2 then gives the columns room. Ship both in one PR.
