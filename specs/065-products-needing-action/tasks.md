# Tasks: Products Needing Action

**Input**: Design documents from `specs/065-products-needing-action/`
**Prerequisites**: plan.md, spec.md, research.md, contracts/missing-filter.md

**Tests**: Included — the constitution (IV) requires behavior changes to land with tests.

## Phase 1: Setup

None. Existing files only; no schema change.

## Phase 2: Foundational

None. User Story 1 contains the only shared piece (the service filter).

## Phase 3: User Story 1 — Filter the product list by missing category/location (P1) 🎯 MVP

**Goal**: `/products?missing=category|location|either` narrows the list; the filter form offers it and keeps it selected.

**Independent Test**: Seed products with both / no category / no location / neither; each filter value lists exactly the expected ones.

- [X] T001 [P] [US1] Add `TestMissingFilter` to tests/unit/test_product_search.py: `category`, `location`, `either`, blank-string category/location count as missing, sub-location without location counts as missing, combines with `tag` (or `q`), empty value is a no-op, unknown value raises `ValidationError` naming `either`
- [X] T002 [US1] Add `missing: Optional[str] = None` to `CatalogService.search_products()` in app/catalog_service.py, document it in the docstring, and implement `_apply_missing_filter(statement, missing)` beside `_apply_stock_filter` (NULL or trimmed-empty = missing; unknown value raises `ValidationError(field='missing')` listing valid values)
- [X] T003 [US1] Pass `request.args.get('missing', '')` through in `product_search()` (into `filters` and the service call) and `api_search_products()` in app/product/routes.py
- [X] T004 [US1] Add a "Missing" `<select id="filter-missing" name="missing">` (Any / No category / No location / Category or location, current value `selected`) to the filter form in app/templates/product/search.html
- [X] T005 [P] [US1] Add e2e tests in tests/e2e/test_products_needing_action.py: choosing a Missing option and applying lists exactly the matching products and the select keeps its value; `/api/products/search?missing=either` agrees with the page

## Phase 4: User Story 2 — "Needs Action" in the Products menu (P2)

**Goal**: Products → Needs Action opens `/products?missing=either`.

**Independent Test**: From any page, open the Products menu, click Needs Action, see only products missing category or location, with the select showing "Category or location".

- [X] T006 [US2] Add the "Needs Action" entry after "All Products" in the Products dropdown in app/templates/base.html, `href="{{ url_for('product.product_search', missing='either') }}"`, icon `bi-exclamation-circle`
- [X] T007 [P] [US2] Add an e2e test in tests/e2e/test_products_needing_action.py: open `#products-nav`, click Needs Action, assert the URL, the selected option, and the listed products

## Phase 5: User Story 3 — Fix gaps with existing tools (P3)

**Goal**: A product given its missing data drops off the filtered list.

- [X] T008 [US3] Add an e2e test in tests/e2e/test_products_needing_action.py: on `?missing=category`, select a product, use the existing bulk Set Category, and after the list reloads the product is gone while the filter stays selected

## Phase 6: Polish

- [X] T009 [P] Document the Missing filter and Products → Needs Action in "Finding Products" in docs/user-manual.md
- [X] T010 Regenerate screenshots (`nox -s screenshots_headless`) and commit only `docs/images/screenshots/user-manual/product_search.png` (baseline churn on the pre-change commit touched 23 shots including this one, so the list diff could not isolate it; it is the one shot whose content this feature changes)
- [X] T011 Run `nox -s tests` and the full `nox -s e2e` (detached); both pass
- [X] T012 Quickstart steps 2–5 are each covered by tests/e2e/test_products_needing_action.py and the unit tests; no separate manual run

## Dependencies

- T002 → T003 → T004; T001 can be written first (fails until T002).
- T005 needs T002–T004. US2 (T006–T007) needs US1. US3 (T008) needs US1.
- T010 needs T004 and T006. T011 last.

## Parallel Opportunities

- T001 and T005 (different test files) can be written alongside T002.
- T009 can be written any time after the contract is fixed.

## Implementation Strategy

MVP is US1 (T001–T005). US2 is a one-line template change on top; US3 adds only a test.
