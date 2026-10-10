# Tasks: Bulk Set Category

**Input**: Design documents from `/specs/063-bulk-set-category/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/set-category.md

**Tests**: Required. Constitution IV says changes that alter behavior land with tests.

## Phase 1: Setup

None. There are no new dependencies and no schema change.

## Phase 2: Foundational (blocks all stories)

- [X] T001 Add `CatalogService.set_category(product_ids, category_path) -> Dict[str, Any]` in `app/catalog_service.py`, near `update_product`. Validate with `_validate_category_path` and refuse a `None` (blank) result with `ValidationError(field='category_path')`. De-duplicate the ids and reject an empty list with `ValidationError`. In one `_session()`, load `Product` rows `WHERE id IN ids`. Raise `ItemNotFoundError` naming any missing ids, before writing anything. Then set `category_path` on each row. Return `{'category_path': canonical, 'products': count}`. Log at info.
- [X] T002 Add `POST /api/products/category` (`api_set_product_category`) in `app/product/routes.py`, next to `api_batch_move_products`. Parse JSON. `product_ids` must be a non-empty list of ints (bool excluded) and `category_path` a string, or the route returns 400 `{'success': False, 'error'}`. Call `set_category`. Map `ValidationError` to 400 and `ItemNotFoundError` to 404. On success, `flash(f'Set category "{c}" on {n} product(s).', 'success')` and return `{'success': True, 'updated': n, 'category_path': c}`.
- [X] T003 [P] Create the dialog macro `bulk_category_modal()` in `app/templates/_bulk_category_modal.html`, with the ids from `contracts/set-category.md`: `#bulkCategoryModal`, `#bulk-category-summary`, `#bulk-category-input` with `maxlength="512"` and `list="bulk-category-suggestions"`, the `#bulk-category-suggestions` datalist, a hidden `#bulk-category-error` alert, Cancel, and `#bulk-category-submit`. Add a header comment like `_bulk_label_modal.html`.
- [X] T004 [P] Create `BulkSetCategoryDialog` in `app/static/js/bulk-set-category.js`. Its constructor takes `{clearSelection}`. `open(productIds)` stores the ids, sets the summary ("N product(s) will be given this category."), clears the input and error, and shows the modal. Submit runs on button click or Enter in the input. A blank input shows an error without a request. Otherwise it sends `csrfFetch('/api/products/category', POST JSON)`. On `response.ok` and `success`, it calls `clearSelection()` and then `window.location.reload()`. Otherwise it shows `error` in `#bulk-category-error`. The submit button is disabled while the request is in flight.
- [X] T005 [P] Fill `bulk-category-suggestions` from `/api/categories` in `app/static/js/catalog-suggestions.js`. This is one more `load(...)` line.
- [X] T006 Unit-test the service and the route in `tests/unit/test_bulk_set_category.py`. Cover: the stored value equals what `update_product` stores for the same raw input (`'Tools / Hand '` → `tools/hand`); a new category is accepted; blank, whitespace and `/` are refused, leaving products unchanged; over-length is refused; a missing id leaves *every* product unchanged; duplicate ids count once; other fields (description, location, quantity) are untouched. Route: 200 with the body and the flash on the next GET; 400 for a bad body or a blank category; 404 for a missing id.

**Checkpoint**: The backend is complete and unit-tested. The dialog exists but no page uses it yet.

## Phase 3: User Story 1 — Products list (P1) 🎯 MVP

**Independent test**: Tick 2 of 3 products, set `tools/hand`. The two show it, the third is unchanged, and nothing is ticked.

- [X] T007 [US1] In `app/templates/product/search.html`, add a `#bulk-category-btn` button (`bi-tags`, "Set Category", disabled) to `page_actions` after Print Labels. Import and render `bulk_category_modal()`. Load `bulk-set-category.js` before `product-list-labels.js`.
- [X] T008 [US1] In `app/static/js/product-list-labels.js`, construct `BulkSetCategoryDialog` with `clearSelection` (untick all boxes, then `onSelectionChange()`). Arm `#bulk-category-btn` in `onSelectionChange`. On click, open the dialog with `selectedEntries().map(e => e.id)`.
- [X] T009 [US1] Add e2e tests in `tests/e2e/test_bulk_set_category.py` (Products). Set a category on 2 of 3 seeded products. After the reload, expect the success alert, the Category cells, the third row unchanged, every checkbox unchecked and the button disabled. Check that suggestions are present (expect the `#bulk-category-suggestions option` count > 0 when a category exists). A blank submit shows the error in the dialog, and after cancelling the boxes stay ticked. Filters are kept after a set (the URL query is unchanged).

## Phase 4: User Story 2 — Order page (P1)

**Independent test**: On an order with 3 lines, tick 2 and set a category. Their products change, the third does not, and nothing is ticked.

- [X] T010 [US2] Add the `#bulk-category-btn` button to `app/templates/product/_order_bulk_toolbar.html`, after Print Labels.
- [X] T011 [US2] In `app/templates/product/order.html`, render `bulk_category_modal()` and load `datalist.js`, `catalog-suggestions.js` (only if not already loaded) and `bulk-set-category.js` before `order-bulk-actions.js`.
- [X] T012 [US2] In `app/static/js/order-bulk-actions.js`, construct the dialog with `clearSelection`, arm `#bulk-category-btn` alongside the other two buttons, and on click open it with `selectedProducts().map(e => e.id)`, which gives distinct products.
- [X] T013 [US2] Add e2e tests for the order page in `tests/e2e/test_bulk_set_category.py`. Tick 2 of 3 lines (two of them naming the same product) and set a category. Expect the flash to count distinct products, the products to carry the category (check through the product detail `#product-category` or the service), receipt state unchanged, and nothing ticked.

## Phase 5: User Story 3 — Outstanding Products (P2)

**Independent test**: Tick one line from each of two orders and set a category. Both products change, both lines remain, and nothing is ticked.

- [X] T014 [US3] In `app/templates/product/outstanding.html`, render `bulk_category_modal()` and load the same scripts as T011. The toolbar button comes from T010.
- [X] T015 [US3] Add an e2e test for Outstanding Products in `tests/e2e/test_bulk_set_category.py`: cross-order set, lines still listed, nothing ticked.

## Phase 6: Polish

- [X] T016 [P] In `docs/user-manual.md`, add a short "Setting a category on several products" section near the product catalog sections, covering the three pages, suggestions, that blank is refused, and that the selection is cleared.
- [ ] T017 Run `nox -s tests` and `nox -s e2e` (detached, at least 20 minutes). Regenerate only the screenshots that show the changed toolbars (Products list, order page, Outstanding Products) with `nox -s screenshots`. Measure the churn, commit only the relevant images, and run `nox -s screenshots_verify`.
- [X] T018 Check `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing, and lint only the touched Python files.

## Dependencies

- T001 → T002 → T006. T003, T004 and T005 are independent of each other and of T001 and T002.
- US1 (T007–T009), US2 (T010–T013) and US3 (T014–T015) each depend on Phase 2. US3 depends on T010 (the shared toolbar) and T012 (the shared script).
- Polish comes last.

## Parallel opportunities

- T003, T004 and T005 run in parallel with T001 and T002.
- Once Phase 2 is done, T007 and T008 (Products) can run in parallel with T010–T012 (order page), because they touch different files.

## Implementation strategy

MVP is Phase 2 plus US1. That is fully usable on the Products list. US2 and US3 are wiring on
top of the shared dialog. Deliver everything in one PR.
