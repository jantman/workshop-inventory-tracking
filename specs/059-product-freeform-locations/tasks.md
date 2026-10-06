# Tasks: Free-Text Locations on the Product Move Page

**Input**: Design documents from `specs/059-product-freeform-locations/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/move-manager.md

**Tests**: The constitution (IV) requires tests for behavior changes. These are e2e, because the behavior lives in the browser.

## Phase 1: Setup

None needed. The change touches existing files only.

## Phase 2: Foundational

- [X] T001 Add a `locationHint` getter to `MoveManager` returning `' (M*, T*, or Other)'`, and use it in the four messages that hard-code `(M*, T*, or Other)` (bulk_location refusal, location-state refusal, `handleIdInput` status, `handleDoneCode` bulk alert). The item page's strings must stay identical. File: app/static/js/move-manager.js
- [X] T002 Add a `location_example` parameter to the `move_page` macro, document it in the header comment, and use it in instruction step 2. Pass `M1-A, T-5, or Other` from app/templates/inventory/move.html. File: app/templates/move/_scan_move.html

## Phase 3: User Stories 1 & 2 — free-text locations on the product page (P1)

**Goal**: Any non-ID text is a product's location wherever the page waits for one.

**Independent Test**: The new tests in tests/e2e/test_product_move.py.

- [X] T003 [US1] Override `isLocation(value)` in `ProductMoveManager` to return true for any non-empty value while `currentExpectedInput` is `location` or `bulk_location`, deferring to `super.isLocation` otherwise. Override `locationHint` to `''`. File: app/static/js/product-move.js
- [X] T004 [US1] Pass a free-text `location_example` (for example `any text, such as WoodshopShelf or Drawer Unit 2`) from app/templates/product/move.html
- [X] T005 [US1] Add an e2e test in which a preselected product (`/products/move?code=…`) is scanned to `eShop Shelf3`, then `Top Bin`, then `>>DONE<<`, and is validated and executed. The product page must then show `eShop Shelf3` / `Top Bin`. Cover two preselected products to `WoodshopShelf` as well. File: tests/e2e/test_product_move.py
- [X] T006 [US2] Add an e2e test that hand-scans code, `WoodshopShelf`, `Drawer 2`, then a second code, `Garage Rack`, `>>DONE<<`. Assert both rows' new location and sub-location. File: tests/e2e/test_product_move.py
- [X] T007 [US1] Add an e2e test that the existing refusals hold: free text before any code is refused, and no product-page alert or the instructions contain `M*`. File: tests/e2e/test_product_move.py

## Phase 4: User Story 3 — item page unchanged (P2)

- [X] T008 [US3] Confirm, without editing them, that the item move e2e tests (tests/e2e/test_move_items*.py, tests/e2e/test_bulk_move_handoff.py) still pass. They pin the item wording and classification.

## Phase 5: Polish

- [X] T009 [P] Update the `scan_on_move_page` docstring to say that the product page's classification depends on its state. File: tests/e2e/waits.py
- [X] T010 [P] Update Moving Products: a location is any text, and the next scan after a location is the sub-location. File: docs/user-manual.md
- [ ] T011 Run `nox -s lint`, `nox -s tests` and the full `nox -s e2e` (detached, given the suite's length).

## Dependencies

T001 and T002 come before T003 and T004. T003 comes before T005–T007. T008 runs alongside T011. T009 and T010 are independent of everything else.

## Implementation Strategy

This is one small increment. US1 and US2 share the single override in T003, so they ship together, and US3 is a regression check.
