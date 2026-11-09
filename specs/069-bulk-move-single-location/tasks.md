# Tasks: Bulk Move to a Single Location by Scanning

**Input**: `specs/069-bulk-move-single-location/` (spec, plan, research, data-model, contracts/move-manager-group.md)

Tests are required by the constitution (Principle IV: behaviour changes land with tests).

## Phase 1: Foundational

- [X] T001 Replace the single `pendingMovesReady` promise with a per-entry `ready` promise; `handleBulkLocationInput()` queues synchronously and patches each row's current location when its `ready` resolves, in app/static/js/move-manager.js
- [X] T002 Make `renderPendingMove()` fill a row in either `#pending-moves` or `#scan-group-rows` in app/static/js/move-manager.js
- [X] T003 [P] Add the `#scan-group` card (count, rows tbody, per-row Remove) to app/templates/move/_scan_move.html per contracts/move-manager-group.md, and update the scan instructions (FR-014)
- [X] T004 [P] Add the same `#scan-group` markup, compact, to app/templates/handheld/move.html

## Phase 2: User Story 1 — scan many, then one location (P1)

**Independent test**: scan three codes, a location, a sub-location, `>>DONE<<`; three rows with the shared destination; execute moves all three.

- [X] T005 [US1] Add the `group_location` state: in `location`, a new ID converts `currentId` + the new ID into `pendingMoves`, renders rows, sets status/badge; in `group_location`, a new ID appends; a location calls `handleBulkLocationInput()` (which hides `#scan-group`) in app/static/js/move-manager.js
- [X] T006 [US1] `ProductMoveManager.isLocation()` treats `group_location` as a location-waiting state in app/static/js/product-move.js
- [X] T007 [US1] Extend `scan_on_move_page` with the new transitions and the wider duplicate check in tests/e2e/waits.py
- [X] T008 [US1] e2e tests: products group + location + sub-location + execute; items group with `M1-A`; group then new ID starts a new group with no sub-location on the first; current locations shown per row — in tests/e2e/test_bulk_scan_group.py

## Phase 3: User Story 2 — one-at-a-time unchanged (P1)

- [X] T009 [US2] Rewrite the tests asserting the abandon rule (tests/e2e/test_product_move.py `test_a_missed_location_abandons_the_first_product`, tests/e2e/test_move_long_session.py, and any other match for "No location was scanned") to assert accumulation instead
- [X] T010 [US2] Confirm the alternating-flow tests (test_move_items*.py, test_move_long_session.py) pass unchanged

## Phase 4: User Story 3 — correcting a group (P2)

- [X] T011 [US3] Duplicate refusal for IDs in `pendingMoves` / equal to `currentId`; `removeFromGroup(id)` (Remove button; last removal returns to `id`); `>>DONE<<`, sub-location (items) refused in `group_location`; `halfEnteredReason()` covers `group_location`; Clear All hides and empties `#scan-group` in app/static/js/move-manager.js
- [X] T012 [US3] e2e tests: duplicate refused; remove one; remove last → Ready; `>>DONE<<` refused with queue still validatable; Clear All; Validate hint — in tests/e2e/test_bulk_scan_group.py

## Phase 5: User Story 4 — handheld (P3)

- [X] T013 [US4] e2e test: two codes then a location on the handheld Move screen queues both, in tests/e2e/test_bulk_scan_group.py (or tests/e2e/test_handheld_move.py)

## Phase 6: Polish

- [X] T014 [P] Document scanning several IDs before one location in docs/user-manual.md (Move Items and Move Products workflow)
- [X] T015 Run `nox -s tests` and `nox -s e2e` (detached) and fix failures
- [ ] T016 Regenerate screenshots, commit only those whose content changed, run `nox -s screenshots_verify`

## Dependencies

T001–T004 → T005–T006 → T007 → T008; T009–T013 after T007. T014 any time. T015–T016 last.

## MVP

Phases 1–2 (US1) plus T009 so the suite is green.
