# Tasks: Move Products Between Locations by Scanning

**Input**: Design documents from `/specs/057-product-location-move/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution IV says behaviour changes land with tests.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None. No new dependency, no schema change.

## Phase 2: Foundational (the shared refactor; blocks every story)

**Goal**: Item Move works exactly as before (FR-012, SC-004), now running on shared code
that the product page can extend.

- [ ] T001 [P] Create `app/utils/batch_move.py` with `parse_moves(data)` (raises `ValueError('Invalid request data')` when the body or `moves` is missing, and `ValueError('No moves provided')` when it is empty or not a list), `destination(location, sub_location) -> (str, str|None)` (strip the location; a stripped sub-location, or None when absent or blank), and `batch_result(moved_count, total, failed) -> dict` (`success`, `moved_count`, `total_count`, `failed_moves`, plus `error: "N items failed to move"` when any failed). Shapes are in contracts/product-move-api.md.
- [ ] T002 [P] Unit tests for T001 in `tests/unit/test_batch_move_utils.py`.
- [ ] T003 Rewire `batch_move_items` in `app/main/routes.py` onto `parse_moves`, `destination` and `batch_result`. Keep every audit call, log message and per-move error string. `tests/unit/test_routes.py::TestBatchMoveAPIWithSubLocation` must pass unchanged.
- [ ] T004 In `app/utils/handoff.py`:
  - rename `parse_ja_ids` → `parse_ids`, which is generic;
  - key rejected entries `{'id', 'reason'}`.

  Update every caller and template that reads `rejected.ja_id`: grep `app/` for `parse_ja_ids`, `rejected_items` and `.ja_id` in templates, including the Shorten page. Also update `tests/unit/test_handoff_parsing.py`.
- [ ] T005 Create `app/static/js/move-manager.js` with `class MoveManager`. Move the whole of today's `InventoryMoveManager` into it, then apply the contracts/move-manager.md renames:
  - `currentJaId` → `currentId`, `bulkGroupJaIds` → `bulkGroupIds`;
  - the `ja_id` / `ja_id_or_sub_location` states → `id` / `id_or_sub_location`;
  - the queue entry's `jaId` → `id`;
  - `data-ja-ids` → `data-ids`, `tr[data-ja-id]` → `tr[data-id]`.

  Then add the subclass hooks: `noun`, `nounPlural`, `idLabel`, `idExample`, `isSubjectId`, `normalizeId`, `isForeignId` (default false), `foreignIdMessage`, `lookup`, `executeUrl`, `moveRequest`. Make the changes below:
  - `classifyInput` returns `'foreign'` before `'location'`. Each state refuses `foreign` with `foreignIdMessage(value)`.
  - Every JA-specific user-visible string is built from `idLabel`, `idExample` and `noun`, so that the item page's strings come out identical to today's.
  - `fetchCurrentLocation` uses `lookup()`. An unset location stays `null`; a thrown lookup gives `'Unknown'`.
  - `validateMoveItem` calls `lookup()` once:
    - found → `{status:'validated', currentLocation, currentSubLocation, itemInfo: label}`;
    - `{found:false}` → `not_found`;
    - throw → `error`.
  - `renderQueueItems` renders a `null` current location as muted "None", and shows `itemInfo` under the ID.
  - `executeMoves` posts `{moves: valid.map(e => this.moveRequest(e))}` to `this.executeUrl`. The confirm and success wording use `nounPlural`.
  - Leave out the `DOMContentLoaded` bootstrap; each page script supplies it.
- [ ] T006 Reduce `app/static/js/inventory-move.js` to `class InventoryMoveManager extends MoveManager`. It implements the item column of contracts/move-manager.md, with `lookup` calling `GET /api/items/{id}` (404 → `{found:false}`, label = `display_name`). Keep the `DOMContentLoaded` → `window.moveManager` bootstrap.
- [ ] T007 Create the macro `move_page(...)` in `app/templates/move/_scan_move.html` holding today's `inventory/move.html` body. Parameterise it by:
  - `noun`, `nouns`, `id_label`, `id_example`, `location_example`;
  - `list_url` / `list_label`, `selection_heading`.

  Render rejected entries from `rejected.id`. Rewrite `app/templates/inventory/move.html` as `{% from "move/_scan_move.html" import move_page with context %}` plus a call whose arguments reproduce today's wording. The scripts block loads `move-manager.js` and then `inventory-move.js`.
- [ ] T008 Update `tests/e2e/waits.py::scan_on_move_page`:
  - drop `_JA_ID` / `_LOCATION`;
  - before typing, read `classifyInput(value)`, `currentExpectedInput`, the queue / pending / `bulkGroupIds` lengths, `currentId !== null`, `idLabel` and the alert count from `window.moveManager`;
  - branch on the returned class (`foreign` behaves like a rejection in every state);
  - build the badge strings from `idLabel`.

  Update the docstring's state names. Update `tests/e2e/test_move_long_session.py` (`currentJaId` → `currentId`) and any other test reading the renamed internals (grep `tests/` for `currentJaId`, `bulkGroupJaIds`, `ja_id_or_sub_location`).
- [ ] T009 Add an assertion that a validated item keeps its real current location, not "Unknown", to `tests/e2e/test_move_current_location_bug.py`. This covers the FR-012 defect fix.

**Checkpoint**: `nox -s tests` passes. The item move e2e files pass with their assertions unchanged.

## Phase 3: User Story 1 — Shelve products by scanning (P1) 🎯 MVP

**Goal**: Scan product → location → optional sub-location, queue, validate, execute.

**Independent Test**: Seed two products (one with no location); scan, validate and execute; check both detail pages.

- [ ] T010 [US1] Add `CatalogService.move_product(code, location, sub_location) -> Product` in `app/catalog_service.py`. It:
  - upper-cases and strips the code;
  - looks it up with `find_product_by_identifier(code, id_type=INTERNAL)`, raising `ItemNotFoundError` if there is none;
  - raises `ValidationError` on a blank location;
  - applies `batch_move.destination`;
  - calls `update_product(product.id, location=…, sub_location=…)`;
  - returns the product.
- [ ] T011 [US1] In `app/product/routes.py` add:
  - `GET /api/products/by-code/<code>`: 200 `{success, product: to_dict()}`, 404 when the value is not shaped like a code or matches no product;
  - `POST /api/products/batch-move`: loops `parse_moves` → `move_product`; missing code or location fails with "Missing product code or location"; `ItemNotFoundError` fails with "Product not found"; `ValidationError` fails with its message; responds with `batch_result`; 400 on `ValueError`;
  - `GET /products/move`: renders `product/move.html` with `resolve_product_handoff(request.args.get('code'), service)`.

  Contract: contracts/product-move-api.md.
- [ ] T012 [US1] Add `resolve_product_handoff(raw, service) -> Handoff` to `app/utils/handoff.py`. For each code from `parse_ids`, it upper-cases the code and accepts it if `is_internal_id` holds and the product exists. Everything else is rejected as `not_found`.
- [ ] T013 [P] [US1] Create `app/static/js/product-move.js` with `class ProductMoveManager extends MoveManager`, following the product column of contracts/move-manager.md:
  - `lookup` → `GET /api/products/by-code/{id}`;
  - label = `description`;
  - `moveRequest` → `{code, new_location, new_sub_location}`;
  - `DOMContentLoaded` bootstrap to `window.moveManager`.
- [ ] T014 [P] [US1] Create `app/templates/product/move.html`, which calls `move_page` with product wording. `list_url` is `product.product_search`. It loads `move-manager.js` and then `product-move.js`.
- [ ] T015 [P] [US1] Add a "Move Products" entry to the Products menu in `app/templates/base.html`, linking `product.product_move`.
- [ ] T016 [P] [US1] Write unit tests in `tests/unit/test_product_move.py`, built through the conftest fixtures. They cover:
  - `move_product`: sets both fields; clears the sub-location when none or blank; strips; leaves other fields alone; unknown code; blank location; lower-case code.
  - The by-code API: 200, 404 for an unknown code, 404 for a malformed one.
  - batch-move: a mix of success and failure; 400s; one failure does not block the others.
  - `/products/move`: renders; the `move` route is not captured by `/products/<product_code>`.
- [ ] T017 [US1] Write e2e tests in `tests/e2e/test_product_move.py`. Seed products with `CatalogService(live_server.storage).create_product(...)` and drive every scan through `waits.scan_on_move_page`. Cover:
  - a product with no location shows current "None";
  - scan → location → sub-location, a second product, then `>>DONE<<`;
  - the "Cleared" marker appears;
  - validate, then execute via `waits.wait_for_move_executed`;
  - the detail pages show `#product-location` / `#product-sub-location`;
  - a lower-case code is accepted.

**Checkpoint**: US1 is fully functional.

## Phase 4: User Story 2 — Scanner mistakes are caught (P2)

**Independent Test**: The refused-input sequences each leave the queue as intended and leave stored locations untouched.

- [ ] T018 [US2] Add e2e tests to `tests/e2e/test_product_move.py`:
  - a location first is refused;
  - a `JA000001` scan is refused (alert names Move Items) and does not become a sub-location;
  - a duplicate product is refused;
  - a product followed by a product abandons the first with a warning;
  - two locations in a row are refused;
  - the half-entered hint appears and Validate is disabled;
  - a made-up `WIT` code validates as `not_found` and Execute stays disabled;
  - remove-from-queue works;
  - deleting a queued product before execute makes that move fail.

  If the last case needs a product delete path that does not exist, cover it at unit level in T016 (batch-move with an unknown code) instead.

## Phase 5: User Story 3 — Move from a product's page (P3)

**Independent Test**: The detail page's Move button opens the Move page with the product awaiting a destination.

- [ ] T019 [US3] Add a Move button to `app/templates/product/detail.html` linking to `url_for('product.product_move', code=product.internal_code)`. Show it only when `product.internal_code` is set, and give it `id="move-product-btn"`.
- [ ] T020 [US3] Add tests:
  - unit, in `tests/unit/test_product_move.py`: `?code=` preselects a known code, lower-case included, and rejects unknown or malformed codes by name;
  - e2e, in `tests/e2e/test_product_move.py`: click the detail page's Move button, `#pending-moves` lists the product, scan a location, and the queue count reaches 1.

## Phase 6: Polish

- [ ] T021 [P] Add a "Moving Products" section to `docs/user-manual.md` next to the Move Items section. Cover the scan sequence, products with no location, sub-location clearing, the detail-page Move button, and that `JA` labels are refused. List "Move Products" under the Products menu.
- [ ] T022 Regenerate screenshots for the changed templates and JS (`nox -s screenshots_headless`). Commit only the move-related images whose change is real, after measuring churn per the project memory, then run `nox -s screenshots_verify`.
- [ ] T023 Run `nox -s tests` and the full `nox -s e2e` (detached, ≥20 min). Both must pass.
- [ ] T024 Check American spelling: `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing.

## Dependencies

- Phase 2 blocks everything. Within it:
  - T001 → T003;
  - T004 → T007;
  - T005 → T006 → T007 → T008/T009.
- US1 (T010 → T011 → T016/T017; T012 → T011; T013, T014 and T015 after Phase 2) is the MVP.
- US2 and US3 depend on US1's page and endpoints. They are independent of each other.
- Polish comes last.

## Parallel Example

After Phase 2: T013, T014 and T015 touch different files and can run together. T016 can be written alongside T010–T012.

## Implementation Strategy

1. Phase 2 first, then prove item Move is unchanged with the unit tests and the item move e2e files.
2. Then US1, which is shippable alone.
3. Then US2 tests, which are mostly confirmation that the shared machine refuses correctly, plus the foreign-ID path.
4. Then US3.
5. Then docs, screenshots, and the full gates.
