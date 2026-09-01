---
description: "Task list for 032-delete-purchase"
---

# Tasks: Delete a Purchase

**Input**: Design documents from `/specs/032-delete-purchase/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/purchase-delete.md)

**Tests**: **Included, and not optional.** Constitution IV requires changes that alter behavior to
land with tests covering that behavior, and both `nox -s tests` and `nox -s e2e` must be green
before merge. Three of this feature's requirements are true only if something checks them —
FR-006 (the photo goes only when unreferenced), FR-007 (the count does *not* move) and FR-012
(all-or-nothing) are all statements about what does **not** happen, and nothing in the code will
keep them true on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1, US2)
- Every task names the exact file it touches

## Path Conventions

Server-rendered Flask application; existing layout kept exactly (plan.md → Structure Decision).
`app/` for source, `app/templates/product/` for views, `tests/unit/` and `tests/e2e/` for tests,
`docs/` for the manual. **No new directory, no new module, no migration.**

## A note on the phase order

**Phase 1 is not "setup" — there is none.** No dependency, directory, migration or config changes,
so the template's Setup phase would be make-work. Phase 1 is the deletion itself, which both
stories sit on top of.

**The split between the phases is where the risk is.** Phase 1 carries all of it: atomicity, the
orphan-photo rule, and the four columns that must *not* move. Phases 2 and 3 are a route, three
templates and their tests. If Phase 1 is right the rest is plumbing; if it is wrong, no amount of
UI makes it safe.

**US1 is Phase 2 and is the MVP.** Stopping after it delivers issue #130's literal ask — deletion
from the product page's purchase history — with the order screen unchanged.

---

## Phase 1: Foundational — the deletion (blocking prerequisite)

**Purpose**: One service method that removes a purchase, its attachments and any photo those
attachments were the last reference to, in one transaction, touching nothing else.

**⚠️ Blocks both user stories.** Neither has anything to call until this exists.

- [X] T001 [P] Add the `PurchaseDeletion` frozen dataclass to `app/models.py` beside `OrderCaptureResult`, with the eight fields data-model.md lists (`purchase_id`, `product_id`, `vendor`, `order_date`, `quantity`, `unit_price`, `supplier_order_reference`, `attachments_deleted`); `unit_price` is typed `Optional[Decimal]` and is never converted to `float` (Constitution III)
- [X] T002 Write the service unit tests in a new `tests/unit/test_purchase_delete.py` covering: an outstanding purchase deleted; a received purchase deleted; the returned `PurchaseDeletion` field-for-field including a `Decimal` `unit_price`; `None` returned for an unknown id; and `attachments_deleted == 0` on a purchase with no files. **Confirm they fail before T005** — issue #129's own guidance, and the only way to know the test is wired to the behavior
- [X] T003 Add to `tests/unit/test_purchase_delete.py` the tests for what must **survive**: the product row with its description, identifiers and specifications; the product's other purchases; product-level attachments (`product_id` set, `purchase_id` NULL); and a photo still referenced by a second `ProductAttachment` or by an `ItemPhotoAssociation` (FR-005, FR-006)
- [X] T004 Add to `tests/unit/test_purchase_delete.py` the tests for what must **not move**: after deleting a *received* purchase against a product with a tracked count, assert `products.quantity`, `quantity_updated_at`, `stock_status` and `stock_status_updated_at` are all byte-for-byte unchanged (FR-007), and assert no `inventory_items` row was read or written (Constitution VI, the check that keeps "not engaged" honest)
- [X] T005 Implement `CatalogService.delete_purchase(purchase_id) -> Optional[PurchaseDeletion]` in `app/catalog_service.py`, following data-model.md's seven-step sequence inside a single `self._session()`: load, collect `photo_id`s, build the summary, `session.delete(purchase)`, `session.flush()`, drop each now-unreferenced photo, commit
- [X] T006 In that method in `app/catalog_service.py`, add the comment research.md R2 requires: the orphan-photo predicate is the **third** statement of one rule, and the other two are `PhotoService.delete_attachment` (`app/photo_service.py:768`) and `cleanup_orphaned_photos` (`app/photo_service.py:327`). Name both, so a future change to the rule finds all three
- [X] T007 Add the atomicity test to `tests/unit/test_purchase_delete.py`: patch the photo deletion to raise part way through, assert the exception propagates **and** that the purchase, its attachment rows and its photos are all still present (FR-012)
- [X] T008 Add the derived-read tests to `tests/unit/test_purchase_delete.py`: after deletion, `get_purchase_history` no longer returns the row, `get_purchase` returns `None`, and `find_order_lines_for` no longer lists it for its order (FR-009 at the service level)
- [X] T009 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green

**Checkpoint**: a purchase can be deleted correctly from Python. Nothing in the UI can reach it yet.

---

## Phase 2: User Story 1 — delete from the product page (Priority: P1) 🎯 MVP

**Goal**: The operator deletes a mis-captured purchase from the product page's purchase history,
behind a confirmation that names it and states its two invisible consequences.

**Independent Test**: Seed a product with two purchases, delete one from the product page, reload,
and confirm one row remains and the other is gone from the history and from the outstanding banner.

**This phase implements the route's `product` redirect only.** The `order` branch belongs to US2,
so US1 ships complete with the order screen untouched.

- [X] T010 [US1] Write the route unit tests in `tests/unit/test_purchase_delete.py`: `GET /purchases/<id>/delete` renders 200 and names the vendor, order date, quantity, price and attachment count; `GET` on an unknown id is a 404 through the existing handler; `POST` deletes and redirects to `product.product_detail`; a second `POST` is a 404 and changes nothing (FR-011)
- [X] T011 [US1] Implement `purchase_delete` (GET and POST) in `app/product/routes.py`, beside `purchase_receive` at `/purchases/<int:purchase_id>/receive`. Thin: load via `service.get_purchase`, read the attachment count via `PhotoService.get_purchase_attachments`, render or call `service.delete_purchase`, flash, redirect. No ORM query and no raw SQL in the route (Constitution II); `ItemNotFoundError` for the missing case, no new error machinery
- [X] T012 [US1] Create `app/templates/product/purchase_delete.html` per contracts/purchase-delete.md: the product linked, the purchase's vendor / order date / quantity / unit price / supplier order reference / line number / received state, **the number of attached files that will go** (stated plainly when it is zero), **the sentence that the product's counted quantity will not change**, a Delete submit carrying `csrf_token()`, and a Cancel that returns changing nothing
- [X] T013 [US1] Add the flash on success in `app/product/routes.py` naming the vendor, order date and quantity and how many files went with it, category `success`, matching `flash('Received.', 'success')` (FR-008)
- [X] T014 [US1] Add the per-row Delete control to `app/templates/product/detail.html` in the existing **Status** cell of `.purchase-row` — not a new column, so the six-column layout and the empty-state row's `colspan="6"` stay correct. Give it a stable class (`delete-purchase-btn`) following `attach-to-purchase-btn` in the same file. No JavaScript
- [X] T015 [US1] Write the E2E tests in a new `tests/e2e/test_purchase_delete.py`: seed via `live_server.add_test_data([...])`, delete one of two purchases, cancel-changes-nothing, the attachment count appearing on the confirmation, and an outstanding purchase leaving the product's on-order banner. Every wait is a navigation or an `expect()`; establish the `#purchase-history` table with `expect()` before any negative assertion, or "the row is gone" passes against a page that has not loaded
- [X] T016 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green

**Checkpoint**: issue #130's literal ask is delivered. A mis-captured purchase is recoverable
without database access, and #129's duplicate can be cleaned up.

---

## Phase 3: User Story 2 — delete from the order screen (Priority: P2)

**Goal**: The operator deletes an orphaned line from the order screen it was sent to, and lands
back on the order.

**Independent Test**: Seed two purchases carrying one order number, open the order screen, delete
one line, and confirm the order re-derives with one line and the purchase is absent from its
product's history too.

- [X] T017 [US2] Add the redirect-branch unit tests to `tests/unit/test_purchase_delete.py`: `return_to=order` redirects to `product.order_detail` with the vendor and order number **taken from the returned `PurchaseDeletion`, not from the request**; `return_to=order` on a purchase with no `supplier_order_reference` falls back to the product page and is not an error; an unrecognized `return_to` value is treated as `product` (research R3)
- [X] T018 [US2] Implement the `return_to` handling in `purchase_delete` in `app/product/routes.py` — two accepted values, `product` (default) and `order`, with the order address built from the deletion summary. Do not accept a URL
- [X] T019 [US2] Thread `return_to` through `app/templates/product/purchase_delete.html` as a hidden field on the POST form and into the Cancel link's target, so cancelling from the order screen returns to the order (FR-002, FR-015)
- [X] T020 [US2] Add the per-line Delete control to `app/templates/product/order.html` on every `.order-line`, beside the existing Receive link — Delete appears on **received** lines too, not only outstanding ones — linking to `GET /purchases/<id>/delete?return_to=order` with the same stable class as T014
- [X] T021 [US2] Add the E2E tests to `tests/e2e/test_purchase_delete.py`: delete a line from the order screen and land back on the re-derived order; the purchase is absent from its product's history; deleting an order's **last** line leaves `/products/orders/<vendor>/<number>` rendering the existing "no purchase is recorded against this order" state rather than an error (FR-010); and the deleted line is gone from **Products → Captured Orders** (FR-009)
- [X] T022 [US2] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green

**Checkpoint**: the orphaned-purchase report's "open the order to look at them" ends in an action.
Both stories work independently.

---

## Phase 4: Polish, gates and validation

**Purpose**: The two CI gates this change trips, the documentation, and the manual pass the issue
is blocking.

- [ ] T023 [P] Document removing a purchase recorded in error in `docs/user-manual.md`, near the purchase-history and captured-orders sections: where the control is on both screens, that attachments go with it, and that the counted quantity does not move and is adjusted by hand
- [ ] T024 Regenerate the screenshots with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless` — required because `app/templates/**` changed, and CI blocks on stale screenshots. **Inspect what actually differs before committing**: screenshots churn on every run from two generators, so commit the images this change really altered rather than everything the run touched
- [ ] T025 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify` and confirm every image is a valid PNG, RGB/RGBA and under 500KB
- [ ] T026 Run the full E2E suite **detached** — `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &` — and poll. It is ~13m45s warm against a 15-minute allowance and most agent bash tools cap at 10 minutes, so running it in the foreground produces a false timeout on a passing run. Budget 20 minutes cold
- [ ] T027 Confirm `git status` is clean after T026. A test session that leaves the working tree dirty is a defect (Constitution IV) — `nox -s e2e` selects `-m "e2e and not screenshot"` precisely so it does not write into `docs/images/screenshots/`
- [ ] T028 Walk the eight manual scenarios in [quickstart.md](./quickstart.md) against a running app (`venv/bin/python run.py`), recording the outcome of each in `specs/032-delete-purchase/verification.md`
- [ ] T029 [P] Open the PR from `issues/130` against `main`, referencing issue #130 and noting the sequencing: #129 should land first or alongside, since this feature is how the operator recovers from the duplicate #129 produces rather than a fix for the duplication
- [ ] T030 Comment on issue #130's parked verification checklist that the blocker is cleared, so the roughly twenty manual checks inherited from #80 can be run

---

## Dependencies

```text
Phase 1 (the deletion) ──┬──► Phase 2 (US1, product page) ──┬──► Phase 4 (gates, docs, validation)
                         │                                   │
                         └──► Phase 3 (US2, order screen) ───┘
```

- **Phase 1 blocks everything.** Both stories call `delete_purchase`.
- **Phase 3 depends on Phase 2**, not on US1 as a story: T018 edits the route T011 creates and T019
  edits the template T012 creates. The *stories* are independent — US1 ships and is useful with
  Phase 3 never built — but the files are shared, so the phases are ordered.
- **Phase 4 needs both**, because T024's screenshots and T028's walkthrough cover both screens.

### Within a phase

- Phase 1: T002 → T005 (write the test, watch it fail, then implement). T003, T004, T007, T008 all
  add to the same new test file and are sequential with each other and with T002. T006 edits the
  method T005 writes. T001 is a different file and is the one genuinely parallel task here.
- Phase 2: T010 → T011 → T012 → T013 (the tests name the behavior; the route, template and flash
  build it up, and T011/T013 are the same function). T014 is a different file but needs T011's
  route name. T015 needs all of them.
- Phase 3: T017 → T018 (same function). T019 and T020 are different templates. T021 needs all four.
- Phase 4: T024 → T025 (verify what was just generated). T026 → T027 (the check is about that run).

### Parallel opportunities

- **T001 ∥ T002**: `app/models.py` and `tests/unit/test_purchase_delete.py`.
- **T019 ∥ T020**: `purchase_delete.html` and `order.html`.
- **T023 ∥ anything in Phases 2 or 3**: `docs/user-manual.md` is touched by nothing else.
- **T029 ∥ T030**: GitHub, not the repository.

`[P]` is sparse and that is honest. This feature is one service method, one route and three
templates; most consecutive tasks share a file, and marking them parallel would be a lie about what
can actually run at once. The unit tests in particular all land in one new file.

## Implementation strategy

**MVP is Phase 1 + Phase 2.** That is issue #130's literal ask — deletion from the product page's
purchase history — and it is what unblocks the duplicate in #129 and the parked verification
checks. The order screen can follow.

**Do not skip Phase 1's negative tests to get to the UI faster.** T004 and T007 are the only things
that will keep FR-007 and FR-012 true: nothing in the code says "the count does not move" or "this
rolls back", so a later refactor that quietly breaks either would otherwise pass every test in the
suite and corrupt inventory data — the one failure Principle I explicitly refuses to trade away.

**Suggested order**:

1. **Phase 1** end to end, tests red first.
2. **Phase 2** → stop and validate against quickstart scenarios 1, 2, 3 and 7. This is a shippable
   increment.
3. **Phase 3** → validate scenarios 4, 5 and 6.
4. **Phase 4**, with T026 started early because it is the long pole.

## Notes

- `[P]` = different files, no dependency on an incomplete task
- No Alembic revision: the schema does not change (research R5)
- No JavaScript: both entry points are plain links to a server-rendered confirmation (research R1)
- Commit after each task or logical group, on `issues/130`
- American spelling throughout — `catalog`, never `catalogue`
