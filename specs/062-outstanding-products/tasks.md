# Tasks: Outstanding Products Page

**Input**: Design documents from `/specs/062-outstanding-products/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/outstanding-page.md

**Tests**: Required. Constitution IV says behaviour changes land with tests: unit tests via
`nox -s tests` and e2e via `nox -s e2e`.

## Phase 1: Setup

No setup. Nothing new to install, configure or migrate.

## Phase 2: Foundational (blocks US2 and US3)

- [ ] T001 Extract the 060 toolbar markup (`#order-bulk-toolbar`: Print Labels button and count, `form#order-receive-form` with csrf, `#bulk-received-date`, `#order-receive-btn`, help text) from `app/templates/product/order.html` into macro `order_bulk_toolbar(action_url)` in `app/templates/product/_order_bulk_toolbar.html`, and call it from `order.html` with `url_for('product.order_receive_lines', …)`. The rendered markup must be unchanged so that `tests/e2e/test_order_bulk_actions.py` and `order-bulk-actions.js` keep working.
- [ ] T002 In `app/catalog_service.py`, move the body of `receive_order_lines` into private `_receive_lines(purchase_ids, received_date, order=None)`, where `order` is an optional `(vendor_name, order_number)` that adds the vendor and order-number filters and the "not on this order" message. Without `order`, a missing id raises `ValidationError("Some ticked lines no longer exist; reload the page", field='purchase_id')`. `receive_order_lines` delegates to it and keeps its signature and behaviour.

## Phase 3: User Story 1 - See everything still on its way (P1) 🎯 MVP

**Goal**: Products → Outstanding Products lists every outstanding purchase, grouped by order, oldest first, with lines that have no order last.

**Independent Test**: Seed two vendors' orders with mixed states and one purchase with no order. Only the outstanding purchases are listed, in contract order.

- [ ] T003 [US1] Add `find_outstanding_purchases() -> List[Purchase]` to `CatalogService` in `app/catalog_service.py`. It returns purchases with `received_date IS NULL`, using `selectinload(Purchase.product)`, sorted in Python by `(no order ref, order_date is None, order_date, vendor, order ref, id)`. A blank `supplier_order_reference` counts as no order.
- [ ] T004 [US1] Add `GET /products/outstanding` route `outstanding_products` in `app/product/routes.py`. It renders `product/outstanding.html` with `title='Outstanding Products'`, `lines`, and `order_count` (the distinct `(vendor, ref)` pairs among lines that have a ref).
- [ ] T005 [US1] Create `app/templates/product/outstanding.html`, extending `product/_layout.html`, per the contract: `#nothing-outstanding` when empty; otherwise `#outstanding-summary`, the toolbar macro posting to `/products/outstanding/receive`, `table#order-lines` with `#order-select-all`, `tr.order-line.outstanding-line` rows (checkbox only when there is a product, `a.order-link` or `span.no-order`, vendor, order date, part, product link or "product deleted", qty, `a.receive-line`), the `bulk_label_modal('orderBulkLabelPrintingModal', 'order-bulk', 'product', 'products')`, and the scripts `label-count.js`, `bulk-label-print.js` and `order-bulk-actions.js`. Add an "All Orders" page action linking to Captured Orders.
- [ ] T006 [US1] Unit tests in `tests/unit/test_outstanding_products.py`: `find_outstanding_purchases` returns only outstanding purchases, across vendors; orders are oldest first, undated orders after dated ones, and no-order lines last; GET renders rows with order links and "no order", and renders the empty state.

## Phase 4: User Story 2 - Receive lines from several orders at once (P1)

**Goal**: Tick lines from any orders, pick a date, and receive them all in one transaction.

**Independent Test**: Tick one line from each of two orders and receive. Both are received on the chosen date, counts rise, and the other lines stay outstanding.

- [ ] T007 [US2] Add `receive_purchases(purchase_ids, received_date=None) -> Tuple[int, int]` to `CatalogService` in `app/catalog_service.py`. It delegates to `_receive_lines` with no order.
- [ ] T008 [US2] Add `POST /products/outstanding/receive` route `outstanding_receive` in `app/product/routes.py`, with the same flash wording as `order_receive_lines`, redirecting to `product.outstanding_products`. Share the flash-building code with `order_receive_lines` in one small helper so the two cannot diverge.
- [ ] T009 [US2] Unit tests in `tests/unit/test_outstanding_products.py`:
  - lines from two orders are received in one call
  - the effects match `receive_purchase` (count += qty, `quantity_updated_at` unchanged, manual flag cleared)
  - already-received lines are skipped
  - a date before one line's order date refuses all of them
  - an unknown id refuses all of them
  - an empty selection is refused
  - the route's flashes and redirect
  - `receive_order_lines` still refuses an id from another order

## Phase 5: User Story 3 - Print labels across orders (P1)

**Goal**: The shared label dialog prints each distinct ticked product once.

**Independent Test**: Tick lines from two orders, including two lines that name the same product. The dialog lists the distinct products and sends one POST per product.

- [ ] T010 [US3] Implementation is covered by T005 (modal, scripts and DOM contract, so `order-bulk-actions.js` drives the dialog). Confirm no script change is needed by reading `app/static/js/order-bulk-actions.js` against the rendered page.

## Phase 6: User Story 4 - Find the page; selection comfort (P2)

- [ ] T011 [US4] Add `<li><a class="dropdown-item" href="{{ url_for('product.outstanding_products') }}"><i class="bi bi-hourglass-split"></i> Outstanding Products</a></li>` to the Products menu in `app/templates/base.html`, next to Captured Orders.

## Phase 7: E2E, docs, screenshot (Polish)

- [ ] T012 [P] E2E tests in `tests/e2e/test_outstanding_products.py`, data seeded directly and waits on `expect` only:
  - lists outstanding lines from two orders plus one no-order line; received lines are absent (establish `#order-lines` first)
  - ticking one line from each order and receiving shows the success flash, and those rows go while the others stay
  - a refused date shows the error flash and leaves all rows
  - Print Labels dedupes across orders: one POST per product, status "Complete: …"
  - the selection arms the buttons, and select-all ticks all rows
  - the Products menu links to the page
- [ ] T013 [P] Add a "### Outstanding Products" section to `docs/user-manual.md` under "## Captured Orders": what is listed, the order, the two actions (same rules as the order page), and the per-line Receive button for amendments. Include the screenshot.
- [ ] T014 Add `test_screenshot_outstanding_products` to `tests/e2e/test_screenshot_generation.py`, seeding outstanding lines on two or three orders, and add its entry to `tests/e2e/screenshot_config.yaml` (`user-manual/outstanding_products.png`). Generate with `nox -s screenshots_headless`, verify with `nox -s screenshots_verify`, and commit only that new image.
- [ ] T015 Run `nox -s tests`, then `nox -s e2e` detached. Both must pass.

## Dependencies

- T001 and T002 come first. T003 → T004 → T005 (US1). T007 needs T002, and T008 needs T007 and T005.
- US3 (T010) needs T005. US4 (T011) is independent.
- The polish tasks follow all stories. T012 and T013 can run in parallel.

## Parallel examples

- T011 (base.html) can be done alongside T003–T005.
- T012 (e2e) and T013 (docs) touch different files.

## Implementation Strategy

MVP is US1 (the list), and it is useful on its own. US2 and US3 deliver what the issue
asks for. Deliver everything in one PR, since the stories together are small.
