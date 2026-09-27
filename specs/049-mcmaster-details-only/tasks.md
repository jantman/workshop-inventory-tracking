# Tasks: McMaster Details-Only Capture

**Input**: Design documents from `/specs/049-mcmaster-details-only/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Requested by the spec (FR-006). Written first and seen failing where the defect
exists today.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None — existing project, no dependencies added.

## Phase 2: Foundational

- [X] T001 Create `tests/unit/test_mcmaster_details_only.py` with module docstring (issue #171), `pytestmark = pytest.mark.unit`, a `catalog` fixture, a McMaster listing payload builder (source_url `https://www.mcmaster.com/91290A115/`, vendor_item_id `91290A115`, two specification rows), and a helper that captures a one-line McMaster order for `91290A115` dated today via `capture_mcmaster_order` (mirroring `tests/unit/test_mcmaster_capture.py`'s `build_order`/`include_all`)
- [X] T002 Add `CatalogService._find_listing_product(item_id, vendor)` in `app/catalog_service.py`: first product carrying `item_id` as each of `VENDOR_SCOPED_TYPES` in order, scoped to `vendor`; None if none

**Checkpoint**: helper exists, nothing calls it yet.

## Phase 3: User Story 1 — Details from an order-created product (P1) 🎯 MVP

**Goal**: product page after a McMaster order offers details-only and applies it.

**Independent Test**: order then product page → confirmation page offers details-only naming the order; submitting it adds rows and records no purchase.

- [X] T003 [US1] Tests in `tests/unit/test_mcmaster_details_only.py`: (a) `find_listing_match(MCMASTER_VENDOR, '91290A115', url)` after an order returns the order-created product, with the order named; (b) GET `/products/capture` with the McMaster listing renders the details-only choice (`intent` radio) rather than only the duplicate warning; (c) POST with `intent=details` adds the specification rows, records no purchase. Run and see (a)/(b) fail
- [X] T004 [US1] `find_listing_match` in `app/catalog_service.py` resolves via `_find_listing_product`

## Phase 4: User Story 2 — Product page first (P1)

**Goal**: product-page capture writes `DISTRIBUTOR`, and is found by its own re-capture and by the order.

- [X] T005 [US2] Tests in `tests/unit/test_mcmaster_details_only.py`: (a) a McMaster product-page capture creates a product with `DISTRIBUTOR` `91290A115` scoped McMaster-Carr and no `VENDOR` one; (b) capturing the same page again offers details-only for that product (and a purchase re-capture lands on it rather than failing or duplicating); (c) the order containing `91290A115` then attaches to that product — one product total. Also (d) a product holding the legacy `VENDOR` McMaster identifier is still found by `find_listing_match`
- [X] T006 [US2] `capture_order` in `app/catalog_service.py` writes `IdentifierType.DISTRIBUTOR` when `vendor_name == MCMASTER_VENDOR`, else `VENDOR`; its `match` lookup resolves via `_find_listing_product`
- [X] T007 [US2] Update `tests/unit/test_mcmaster_routes.py` product-page tests (lines ~334, ~361, ~564 and the class docstring that records 028 §A6's deviation) to look up `DISTRIBUTOR` and state that the write now matches 028 FR-012

## Phase 5: User Story 3 — Purchase after an order (P2)

- [X] T008 [US3] Test in `tests/unit/test_mcmaster_details_only.py`: after a McMaster order, a product-page purchase capture (with `acknowledged_duplicate_of` answering the duplicate question) raises the matched-product question or attaches, never creates a second product for `91290A115`

## Phase 6: Polish & Cross-Cutting

- [X] T009 [P] Edge-case tests in `tests/unit/test_mcmaster_details_only.py`: Amazon product-page capture still writes `VENDOR`; a `DISTRIBUTOR` `91290A115` held for DigiKey is not matched by a McMaster capture; a DigiKey paste capture with a typed DigiKey part number finds the DigiKey-order product
- [X] T010 Rewrite `_mcmaster_product_by_part_number`'s docstring in `app/catalog_service.py`: both kinds are tried because products recorded as `VENDOR` before feature 049 must still be found; remove the "editing capture_order was rejected" rationale
- [X] T011 Run `nox -s tests` and `nox -s lint`; fix failures
- [X] T012 Run `nox -s e2e` detached (≥20 min); confirm pass and a clean working tree
- [X] T013 The repository spelling check in CLAUDE.md returns nothing for touched files

## Dependencies

T001, T002 → US1 (T003 → T004) → US2 (T005 → T006 → T007) → US3 (T008) → Polish.
US3 relies on T006's widened `capture_order` match. T009 is parallel with T010.

## Implementation Strategy

MVP is US1 (T001–T004): it alone unblocks the reported workflow. US2 makes the write agree
with 028 and must land in the same PR, because it changes which kind `capture_order`'s own
lookup has to find.
