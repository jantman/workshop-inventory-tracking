# Tasks: McMaster Order Details Checklist

**Input**: Design documents from `specs/050-mcmaster-details-checklist/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/order-page.md

**Tests**: Required — the constitution (IV) requires behaviour changes to land with tests,
and FR-008 asks for e2e coverage.

## Phase 1: Setup

None — existing project, no new dependencies.

## Phase 2: Foundational (blocks both stories)

- [X] T001 Add optional `listing_url: Optional[Callable[[str], str]] = None` to `OrderVendor`, documented as "the vendor's product-listing address from a line's item id; its presence is what puts the details checklist on the order page", in app/services/order_vendors.py
- [X] T002 Move `_amazon_listing_url` from app/product/routes.py to app/catalog_service.py beside the Amazon vendor functions, add `_mcmaster_listing_url(part) -> f'https://www.mcmaster.com/{part}/'` beside the McMaster ones, and register each as `listing_url=` on `AMAZON_ORDER_VENDOR` and `MCMASTER_ORDER_VENDOR` (DigiKey registers none) in app/catalog_service.py
- [X] T003 Point `_missing_details_link` at `AMAZON_ORDER_VENDOR.listing_url` (behaviour unchanged, 044 FR-018) in app/product/routes.py

## Phase 3: User Story 1 — Work through a McMaster order's products (P1) 🎯 MVP

**Independent test**: a McMaster order page with detail-less products shows the progress banner, "missing" marks and `https://www.mcmaster.com/<part>/` links.

- [X] T004 [US1] Replace the `vendor == AMAZON_VENDOR` gate with `order_vendor is not None and order_vendor.listing_url is not None and bool(lines)`, rewrite the 044 US3 comment to give the real reason (products created without details, listing address buildable from the line's item id), and pass `listing_url=` the vendor's builder in place of `amazon_listing_url` in `order_detail` in app/product/routes.py
- [X] T005 [US1] Call `listing_url(purchase.vendor_item_id)` instead of `amazon_listing_url(...)` in app/templates/product/order.html
- [X] T006 [P] [US1] Unit tests: McMaster order of two detail-less products reads "2 of 2", two `details-missing`, hrefs `https://www.mcmaster.com/<part>/`; filling one moves to "1 of 2" and drops its link — in tests/unit/test_order_product_details.py
- [X] T007 [P] [US1] E2E test mirroring `test_the_order_page_walks_through_each_product` for McMaster: seed two McMaster purchases on one order through the service, open `/products/orders/McMaster-Carr/<order>`, expect "2 of 2", two `a.open-listing` with McMaster hrefs; fill one via `apply_listing_details`, reload, expect "1 of 2" and `.details-captured` — in tests/e2e/test_order_product_details.py

## Phase 4: User Story 2 — Other vendors unchanged (P1)

**Independent test**: Amazon checklist tests pass unmodified; DigiKey and hand-recorded vendors' order pages show no checklist.

- [X] T008 [US2] Replace `test_another_vendors_order_page_is_unchanged` (which asserts McMaster has no checklist — now wrong) with DigiKey and unregistered-vendor cases asserting no `#details-progress` and no `details-missing`, in tests/unit/test_order_product_details.py
- [X] T009 [P] [US2] E2E: a DigiKey order page seeded through the service shows `#order-lines` and no `#details-progress`, in tests/e2e/test_order_product_details.py

## Phase 5: Polish

- [X] T010 Update the module docstring of tests/e2e/test_order_product_details.py to say it covers McMaster's checklist too
- [X] T011 Run `nox -s tests` and `nox -s e2e` (detached, ≥20 min) and confirm the tree is clean afterward
- [X] T012 Check user docs for an Amazon-only description of the order checklist (`grep -rn "Open listing\|still need details" docs/ README.md`) and correct it

## Dependencies

T001 → T002 → T003; T002 → T004 → T005. T006/T007 need T005. T008/T009 need T004. US1 and US2 are independent once Phase 2 and T004 land.

## Parallel opportunities

T006 ∥ T007; T008 ∥ T009 (different files).

## Implementation strategy

MVP is US1 (T001–T007). US2 is the regression guard and lands in the same PR.
