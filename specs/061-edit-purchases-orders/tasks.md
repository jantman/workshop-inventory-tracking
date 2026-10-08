# Tasks: Edit Purchases and Orders

**Input**: Design documents from `/specs/061-edit-purchases-orders/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/edit-routes.md

**Tests**: Required — Constitution IV: behaviour changes land with tests.

## Phase 1: Setup

No setup: no dependency, schema or configuration change.

## Phase 2: Foundational

- [X] T001 Add `_keep_time_if_same_day(new, stored)` module helper (R7) next to `_parse_datetime` in app/catalog_service.py

## Phase 3: User Story 1 — Correct a purchase in place (P1) 🎯 MVP

**Goal**: Every captured field of a purchase is editable from the product page and the order page.

**Independent Test**: Edit a seeded order line's quantity and price; both pages show the new values; it is still on its order.

- [X] T002 [US1] Implement `CatalogService.update_purchase(purchase_id, **fields)` in app/catalog_service.py: validate every field before writing (vendor required; quantity; prices; pack both-or-neither/size ≥ 2; order line number > 0; received date only on a received purchase, may be cleared; received not before ordered), absent field = unchanged, blank = cleared; never touch the product; return None for an unknown id
- [X] T003 [US1] Add `purchase_edit` GET/POST route `/purchases/<int:purchase_id>/edit` with `return_to` flag and redirect/cancel helpers in app/product/routes.py
- [X] T004 [US1] Create app/templates/product/purchase_edit.html (all FR-002 fields pre-filled from purchase or redisplayed form_data; received date only when received; link to Receive when outstanding)
- [X] T005 [P] [US1] Add `.edit-purchase-btn` to the purchase history row in app/templates/product/detail.html
- [X] T006 [P] [US1] Add `.edit-purchase-btn` (`return_to=order`) to each line in app/templates/product/order.html
- [X] T007 [US1] Unit tests for `update_purchase` validation, no stock effects, attachments/vendor_order_id preserved, same-day time kept, and the route (pre-fill, save, redirect, refusal redisplay, 404) in tests/unit/test_purchase_edit.py
- [X] T008 [US1] E2E: edit from the product page and from the order page (lands back on the order, line still listed) in tests/e2e/test_purchase_edit.py

## Phase 4: User Story 2 — Re-attach a purchase to its order (P1)

**Goal**: Setting vendor/order number/line on a purchase moves it onto an order.

**Independent Test**: A hand-recorded purchase edited to an existing order's number appears on that order's page.

- [X] T009 [US2] Enforce order-line-number uniqueness within (vendor, supplier order number) when changed (R5) in `update_purchase` in app/catalog_service.py
- [X] T010 [US2] Unit tests: re-attach, move between orders, line-number conflict refused, unchanged duplicate tolerated in tests/unit/test_purchase_edit.py
- [X] T011 [US2] E2E: re-attach a hand-recorded purchase to an order in tests/e2e/test_purchase_edit.py

## Phase 5: User Story 3 — Correct a whole order (P2)

**Goal**: Order number, order date and customer reference edited for all lines in one save.

**Independent Test**: Edit Order changes date and number of a three-line order; new page lists three lines with the new date.

- [X] T012 [US3] Implement `CatalogService.update_order(vendor_name, order_number, new_order_number, order_date, order_reference) -> int` in app/catalog_service.py (one session; number required; rename onto existing order refused; date not after any received date; same-day time kept per line)
- [X] T013 [US3] Add `order_edit` GET/POST route `/products/orders/<vendor>/<order_number>/edit` in app/product/routes.py (pre-fill and "lines disagree" note computed from the loaded lines)
- [X] T014 [US3] Create app/templates/product/order_edit.html and add `#edit-order-btn` page action to app/templates/product/order.html
- [X] T015 [US3] Unit tests for `update_order` and the route in tests/unit/test_purchase_edit.py
- [X] T016 [US3] E2E: Edit Order changes date and number; lands on new address in tests/e2e/test_purchase_edit.py

## Phase 6: Polish

- [X] T017 [P] Document editing a purchase and an order under "Recording Purchases" in docs/user-manual.md
- [X] T018 Run `nox -s tests` and `nox -s e2e`; confirm `grep -ric catalogue README.md docs/ app/ tests/` is empty and the working tree is clean

## Dependencies

- T001 → T002 → T003/T004 → T005/T006 → T007/T008
- US2 builds on `update_purchase` (T002); US3 needs only T001.
- Polish after all stories.

## Parallel Opportunities

- T005 and T006 (different templates); T017 alongside any story.

## Implementation Strategy

MVP is US1 (it already satisfies most of US2 by letting the order number be edited). Then US2's
uniqueness guard, then US3. One PR for all three.
