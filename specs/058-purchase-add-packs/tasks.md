# Tasks: Pack Quantity on Record a Purchase

**Input**: Design documents from `/specs/058-purchase-add-packs/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/purchase-add-form.md

**Tests**: Included. Constitution IV requires behaviour changes to land with tests.

## Phase 1: Setup

No setup is needed: there are no new dependencies and no schema change.

## Phase 2: Foundational

- [ ] T001 Extract the pack arithmetic out of `capture_order` into `CatalogService._apply_pack(count, price, packs, pack_count, paid_per_pack, rendered_count=None, rendered_price=None)`, which returns `(count, price)`, in app/catalog_service.py. `capture_order` calls it with its rendered defaults. Its behaviour must not change, and the existing `tests/unit/test_capture.py::TestAPackListingRecordsItems` must still pass.

**Checkpoint**: The capture path is unchanged. Run `nox -s tests`.

## Phase 3: User Story 1 — Record a pack purchase by hand (P1) 🎯 MVP

**Goal**: Record a Purchase accepts Packs Bought, Paid for the Pack and Units in the Pack, derives Quantity and Unit Price live, and stores the vendor pack line.

**Independent Test**: Post 2 × 100 @ 13.23 with Quantity and Unit Price empty. The result is 200 @ 0.13, pack 100 @ 13.23.

- [ ] T002 [US1] Add `CatalogService.record_purchase_with_pack(product_id, packs=None, pack_size=None, pack_price=None, quantity=None, unit_price=None, **fields)` per contracts/purchase-add-form.md, in app/catalog_service.py. It validates, calls `_apply_pack` with no rendered defaults, then calls `record_purchase(..., **_pack_fields(self, pack_count, paid))`.
- [ ] T003 [US1] Make `purchase_new` forward `packs`, `pack_size` and `pack_price` and call `record_purchase_with_pack`, in app/product/routes.py.
- [ ] T004 [US1] In app/templates/product/purchase_add.html, add the Packs Bought / Paid for the Pack / Units in the Pack row (same ids, names and defaults as capture.html; values from `form_data`) and the `#unit-price-inexact` and `#unit-price-error` notes under Unit Price. Add "How many items this brings in, not how many packs." help under Quantity, and load `js/pack-unit-price.js`.
- [ ] T005 [P] [US1] Update the header comment of app/static/js/pack-unit-price.js to say that Record a Purchase is now a second host.
- [ ] T006 [P] [US1] Write unit tests in tests/unit/test_purchase_add_packs.py for: 2×100@13.23 → 200@0.13 with pack kept; a typed quantity wins; a typed unit price wins; blank packs counts as 1; a pack size without a price derives quantity only and stores no pack; a bad pack size or pack price is refused and records nothing, with the form re-rendered with its values.
- [ ] T007 [P] [US1] Write e2e tests in tests/e2e/test_purchase_add_packs.py: filling the pack fields shows Quantity 200, Unit Price 0.13 and the rounding note, and saving records 200 @ 0.13 in the purchase history. Wait with `expect(...).to_have_value`.

## Phase 4: User Story 2 — Recording a single item is unchanged (P2)

**Goal**: A hand purchase with the default pack fields records exactly what it did before.

**Independent Test**: Post Quantity 5 and Unit Price 2.00 with the defaults. The result is 5 @ 2.00 with no pack.

- [ ] T008 [P] [US2] Add unit tests in tests/unit/test_purchase_add_packs.py for: the default pack fields (`packs=1`, `pack_size=1`, empty `pack_price`) give 5 @ 2.00 and NULL pack columns; a pack size of 1 with a pack price stores no pack; a POST without any pack fields (an older form) still works.

## Phase 5: Polish

- [ ] T009 [P] Update docs/user-manual.md "Recording Purchases" to say that Add Purchase has the same pack fields as capture, and point to "When it is sold as a pack".
- [ ] T010 Check whether any screenshot test renders the Record a Purchase form (`grep -rn "purchases/new" tests/`). If one does, regenerate the screenshots with `nox -s screenshots_headless` and commit only the changed images.
- [ ] T011 Run `nox -s tests` and `nox -s e2e` (detached, with a 20+ minute budget).

## Dependencies

- T001 → T002 → T003. T004 is independent of T002/T003 but must land before T007.
- US2 depends on T002 and T003 only.
- T005, T006, T008 and T009 can run in parallel once their targets exist.

## Implementation Strategy

US1 is the MVP and the whole of the issue. US2 is a regression guard on the same code.
