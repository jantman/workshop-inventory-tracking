# Tasks: JA IDs in the Header Scan Box

**Input**: Design documents from `specs/067-scan-box-ja-id/`

**Tests**: Included — constitution IV requires behavior changes to land with tests.

## Phase 1: Setup

None — no new dependencies or project structure.

## Phase 2: Foundational

- [X] T001 Add `ScanKind.JA_ID` and list `'item'` among `ScanResolution` outcomes (docstring) in app/models.py
- [X] T002 [P] Create `normalize_ja_id(value: str) -> Optional[str]` (strip, `^JA[0-9]{6}$` case-insensitive, returns uppercase or None; never raises on str) in app/utils/ja_id.py

## Phase 3: User Story 1 — Scan a JA ID into the header scan box (P1) 🎯 MVP

**Goal**: A JA ID entered in `#global-scan-input` opens `/inventory/edit/<JA ID>`.

**Independent test**: Seed an item, enter its JA ID in the scan box, land on its edit page.

- [X] T003 [US1] Add rule 0 (JA ID → `ScanKind.JA_ID`, value uppercased/stripped) ahead of rule 1 and update the module docstring in app/utils/scan_router.py
- [X] T004 [US1] Return `ScanResolution('item', classification)` for `ScanKind.JA_ID` and update the docstring's outcome list in app/catalog_service.py `resolve_scan`
- [X] T005 [US1] Map outcome `'item'` to `url_for('main.inventory_edit', ja_id=classification.value)` and update the docstring in app/product/routes.py `api_scan`
- [X] T006 [P] [US1] Update the `resolve()` comment that says every scan ends at a product in app/static/js/scan-capture.js
- [X] T007 [P] [US1] Unit tests: JA ID classifies `JA_ID` (upper, lower, whitespace); `JA12345`, `JA1234567`, `JA000123 bolt`, `XJA000123` do not; in tests/unit/test_scan_router.py
- [X] T008 [P] [US1] Unit test: `JA_ID` resolves to `'item'` with `product` None, even when a vendor identifier with that value exists, in tests/unit/test_scan_resolution.py
- [X] T009 [P] [US1] Unit test: `POST /api/scan` with `ja000123` returns `outcome == 'item'` and `url == '/inventory/edit/JA000123'` in tests/unit/test_scan_routes.py
- [X] T010 [US1] Rewrite e2e tests against `#global-scan-input` (existing item, nonexistent item → "not found", lowercase input, malformed JA ID → product search) seeding via `live_server.add_test_data`, in tests/e2e/test_ja_id_lookup.py
- [X] T011 [US1] Switch the inactive-item tests from `#ja-id-lookup` to `#global-scan-input` in tests/e2e/test_edit_inactive_item_via_search.py

## Phase 4: User Story 2 — One box in the header (P2)

**Goal**: The JA ID Quick Lookup box and everything serving only it are gone.

**Independent test**: Any page's header contains `#global-scan-input` and no `#ja-id-lookup`.

- [X] T012 [US2] Remove the JA ID Quick Lookup block and mention JA IDs in the scan box `title` in app/templates/base.html
- [X] T013 [P] [US2] Remove `setupJaIdLookup` and its call in `init` in app/static/js/main.js
- [X] T014 [P] [US2] Remove the `#ja-id-lookup` rules in app/static/css/main.css
- [X] T015 [P] [US2] Add a JA ID row to the scanning table and a sentence that the scan box opens inventory items in docs/user-manual.md
- [X] T016 [US2] e2e assertion that the header has no `#ja-id-lookup` (after establishing `#global-scan-input` visible) in tests/e2e/test_ja_id_lookup.py

## Phase 5: Polish

- [X] T017 `grep -rn "ja-id-lookup\|setupJaIdLookup\|JA ID Quick" app docs README.md` returns nothing (tests/ names it only in the absence assertion)
- [X] T018 Run `nox -s tests`, then `nox -s e2e` detached
- [X] T019 Regenerate screenshots (`nox -s screenshots_headless`); commit only images where the header change is visible, discard per-run churn

## Dependencies

- T001, T002 → T003 → T004 → T005; tests T007–T009 after their code.
- US2 (T012) after US1 is in place, so the capability is never lost.
- T017–T019 last.

## Parallel examples

- T002 alongside T001; T006–T009 together; T013–T015 together.

## Implementation strategy

MVP = Phase 2 + US1. US2 is the removal and docs. Single PR.
