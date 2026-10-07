# Tasks: Bulk Receive and Bulk Label Printing on the Order Page

**Input**: Design documents from `/specs/060-order-bulk-receive-labels/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/order-bulk-actions.md

**Tests**: Included — the constitution (IV) requires behavior changes to land with tests.

## Phase 1: Setup

No setup: existing app, no new dependencies.

## Phase 2: Foundational (blocks US1)

- [X] T001 Extract the receipt effects of `receive_purchase` (set `received_date` when unset, raise a tracked count by `purchase.quantity`, clear a manual stock flag and its date) into `CatalogService._apply_receipt(session, purchase, product, received)` in app/catalog_service.py, with `receive_purchase` calling it; behavior unchanged (existing tests in tests/unit/test_order_receive.py and the receive suites are the gate)

## Phase 3: User Story 1 — Receive several lines at once (P1) 🎯 MVP

**Goal**: Tick lines, pick a date, receive them all with their ordered quantities.
**Independent test**: three outstanding lines, receive two → two received on that date, third outstanding, counts raised.

- [X] T002 [US1] Add `CatalogService.receive_order_lines(vendor_name, order_number, purchase_ids, received_date=None) -> Tuple[int, int]` in app/catalog_service.py: one session; refuse no ids / ids not on the order / unreadable date / date before any ticked outstanding line's order date (nothing persisted); call `_apply_receipt` for outstanding lines; count already-received as skipped
- [X] T003 [US1] Add `POST /products/orders/<vendor>/<order_number>/receive` route `order_receive_lines` in app/product/routes.py: read `purchase_id` list and `received_date`, call the service, flash per contract, redirect to `product.order_detail`
- [X] T004 [US1] In app/templates/product/order.html add `#order-bulk-toolbar` with `form#order-receive-form` (csrf, `#bulk-received-date` blank=today, `#order-receive-btn`), a select-all header column, and `input.order-line-checkbox[name=purchase_id][form=order-receive-form]` per line with a product (with `data-product-id`, `data-product-label`)
- [X] T005 [P] [US1] Unit tests in tests/unit/test_order_bulk_receive.py: parity with single `receive_purchase` (count, unchanged count date, cleared manual flag), received date applied, blank = now, already-received skipped, all-or-nothing on early date, id from another order refused, no ids refused, route flash + redirect, page renders checkboxes only for lines with a product and none for an empty order

## Phase 4: User Story 2 — Print labels for several products at once (P1)

**Goal**: Tick lines, print their products' labels from the shared dialog.
**Independent test**: tick two lines → dialog lists two products; one label POST each; duplicate product printed once.

- [X] T006 [US2] Add `#order-print-labels-btn` with `#order-selected-count` to the toolbar and `bulk_label_modal('orderBulkLabelPrintingModal', 'order-bulk', 'product', 'products')` plus script tags (label-count.js, bulk-label-print.js, order-bulk-actions.js) in app/templates/product/order.html
- [X] T007 [US2] Create app/static/js/order-bulk-actions.js: `BulkLabelPrintDialog` with `printOne` posting to `/api/products/<id>/label` via `csrfFetch`; selection read from the checkboxes at open time and deduplicated by product id

## Phase 5: User Story 3 — Selection that reads clearly (P2)

- [X] T008 [US3] In app/static/js/order-bulk-actions.js: select-all with tri-state (`indeterminate`), selected count badge, and both `#order-print-labels-btn` and `#order-receive-btn` disabled while nothing is ticked
- [X] T009 [US1] [US2] [US3] E2E tests in tests/e2e/test_order_bulk_actions.py (seed purchases directly; wait with `expect`): bulk receive two of three lines shows received states and flash; received+outstanding ticked reports skipped; label dialog lists deduplicated products and posts one label per product; buttons disabled with nothing ticked; select-all ticks every line

## Phase 6: Polish

- [X] T010 [P] Document the two bulk actions in the order page section of docs/user-manual.md
- [ ] T011 Run `nox -s tests` and `nox -s e2e` (detached); confirm the working tree is clean afterward and `grep -ric catalogue README.md docs/ app/ tests/` is empty

## Dependencies

T001 → T002 → T003 → T004 → T005. T006/T007 depend on T004 (checkbox markup). T008 extends T007. T009 needs T004–T008. T010 independent. T011 last.

## Parallel opportunities

T005 alongside T006–T007 (different files); T010 any time.

## Implementation strategy

MVP = Phase 2 + US1 (bulk receive). US2 and US3 then layer the label dialog and selection polish on the same checkboxes.
