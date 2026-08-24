---

description: "Task list for Stock Fit Search"
---

# Tasks: Stock Fit Search

**Input**: Design documents from `specs/027-stock-fit-search/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/fit-rules.md](./contracts/fit-rules.md), [contracts/find-stock-api.md](./contracts/find-stock-api.md)

**Tests**: **Required, not optional.** Constitution Principle IV: "Changes that alter behavior
MUST land with tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST pass
before a change is merged." Test tasks below are part of the deliverable, not a suggestion.

**Organization**: Grouped by user story. Each story is a working increment: after Foundational
+ US1 the reported bug is fixed and shippable; US2, US3 and US4 each add a distinct capability
without touching what came before.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file, no dependency on an incomplete task
- **[Story]**: US1–US4, mapping to the user stories in [spec.md](./spec.md)

## Path Conventions

Brownfield Flask application, existing layout. Sources under `app/`, tests under `tests/unit/`
and `tests/e2e/`. See the tree in [plan.md](./plan.md#source-code-repository-root).

**Every nox invocation below assumes** `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` and the
repository virtualenv's binaries invoked by path (`venv/bin/nox`), never `source venv/bin/activate`.

---

## Phase 1: Setup

**Purpose**: Know the suite is green before changing it, and create the one new module.

- [X] T001 Capture a green baseline: run `venv/bin/nox -s tests` and save the output to `/tmp/027-baseline-tests.log`. A failure here is pre-existing and must be understood before proceeding — do not start work against a red suite.
- [X] T002 [P] Create `app/utils/fit.py` with a module docstring stating the two invariants that govern it: pure functions only (no Flask, no SQLAlchemy, no storage) and `Decimal` only, never `float`. Define `PI = Decimal('3.14159265359')` with a comment noting it is the constant `Dimensions.volume()` already uses in `app/models.py` and that it appears only in the sort key, never in a displayed figure.

**Checkpoint**: Baseline recorded, new module exists and imports cleanly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Everything the four stories share — envelope derivation, the request type, the
query and its counters, the two routes, the page, and the shared-table column. No fit rule and
no ordering is implemented here; those are the stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### The domain module

- [X] T003 [P] Define the envelope types in `app/utils/fit.py`: frozen dataclasses `Box(a, b, c)` and `Cylinder(diameter, height)`, and a `SkipReason` enum with members `HOLLOW` and `INCOMPLETE`. Fields are `Decimal`; the `Box` field names imply no ordering — the fit rules sort.
- [X] T004 Implement `envelope_for(item)` in `app/utils/fit.py`, applying rules E1–E6 of [contracts/fit-rules.md §1](./contracts/fit-rules.md) **in order**, returning either an envelope or a `SkipReason`. Note in a comment that E2 must precede E3 so a round plate carrying a stale `length` is still read as a disc. Depends on T003.
- [X] T005 [P] Define `RequestedPiece` in `app/utils/fit.py` — frozen dataclass carrying `shape` (`RECTANGULAR` or `ROUND` only), `dimensions` and `tolerances` dicts, with the four validation rules from [data-model.md §1](./data-model.md): every required dimension present, every dimension `> 0`, every tolerance `>= 0`, every tolerance `<` its dimension. Add `effective(name)`. Tolerances are accepted and validated here but not yet *applied* — that is US4.
- [X] T006 Add `tests/unit/test_fit.py` covering every row of the envelope table in [contracts/fit-rules.md §1](./contracts/fit-rules.md) — all fourteen type/shape combinations, plus a hollow row, plus a row missing a needed dimension for each of E2–E5. Depends on T004.
- [X] T007 Add the D3 agreement test to `tests/unit/test_fit.py`: walk every combination `TypeShapeValidator` declares compatible and assert `envelope_for` reads exactly the fields taxonomy requires for it, or returns `INCOMPLETE` — never reads a field taxonomy does not require, and never silently returns nothing for a combination taxonomy describes. This test is what keeps the two tables from drifting; do not weaken it. Depends on T006 (same file).
- [X] T008 Add `RequestedPiece` validation tests to `tests/unit/test_fit.py` — each of the four rules, rejected and accepted. Depends on T007 (same file).

### Service and routes

- [X] T009 Implement `InventoryService.find_stock(request)` in `app/mariadb_inventory_service.py` returning `FindStockResult(items, considered, skipped_incomplete, skipped_hollow)`. One query: `active == True` and `material.in_(get_material_descendants(...))`, matching the legacy `Query` style of the surrounding file. Derive an envelope per candidate, tally the two skip reasons, and call into `app/utils/fit.py` for the fit test. Do **not** modify `search_active_items` (FR-026).
- [X] T010 Add `find_stock` tests to `tests/unit/test_mariadb_inventory_service.py`: hierarchical material matching, active-only (an inactive row of the right size is absent), and each of the three counters against a seeded set containing a tube and a row with a NULL dimension. Depends on T009.
- [X] T011 Add `GET /inventory/find-stock` and `POST /api/inventory/find-stock` to `app/main/routes.py` per [contracts/find-stock-api.md](./contracts/find-stock-api.md). Parse, validate, call the service, jsonify — no SQL and no ORM in the route (Principle II). Mirror `api_advanced_search`'s `@csrf.exempt`, its 400 body shape, and its 500 logging. There is no `active` parameter (D15). Depends on T009.
- [X] T012 Add route tests to `tests/unit/test_routes.py`: each of the six 400 cases in [contracts/find-stock-api.md](./contracts/find-stock-api.md), asserting the message names the offending field; and one success case asserting the payload carries every key the shared table reads. Depends on T011.

### Page and shared table

- [X] T013 [P] Add `show_fit_column` to the `render_inventory_table` macro in `app/templates/inventory/_item_table.html` — one extra header in both the sortable and non-sortable branches, absent by default so `list.html` and `search.html` are unaffected (FR-028).
- [X] T014 Add `showFitColumn` to `app/static/js/components/inventory-table.js`: default `false` in the constructor config, and one `<td>` in `createRow()` rendering from `item.fit`. The cell body is filled in by US1 (T024); here it only has to exist and be gated. Do not touch `setItems()` — its not calling `sortBy()` is what preserves the server's order (FR-029). Depends on T013.
- [X] T015 [P] Create `app/templates/inventory/find-stock.html`: the request form (material with the same hierarchical selector the advanced search uses, a shape choice, and the rectangular dimension inputs), a results region with a counters line and a no-results message, and the shared macro called with `show_fit_column=True`. The round shape option and the tolerance inputs come later (T031, T041).
- [X] T016 Create `app/static/js/inventory-find-stock.js`: submit handler, `fetch` to `/api/inventory/find-stock`, `InventoryTable.setItems(items)` importing the same component `inventory-search.js:12` imports. Depends on T014, T015.
- [X] T017 Render the counters and the empty state in `app/static/js/inventory-find-stock.js`: on every search show `considered`, `skipped_incomplete` and `skipped_hollow`, and when `items` is empty say so plainly alongside those counts (FR-023, SC-006). Depends on T016.
- [X] T018 [P] Add the nav entry to `app/templates/base.html` — "Find Stock for a Part" under the Inventory dropdown, beside "Search Items" (`:53`).
- [X] T019 [P] Create `tests/e2e/pages/find_stock_page.py`, a page object over `InventoryTableMixin` and `BasePage` following `tests/e2e/pages/search_page.py`. Waits live here, assertions live in the tests. No `wait_for_timeout`, no `time.sleep`.
- [X] T020 Create `tests/e2e/test_find_stock.py` with the FR-028 no-regression check only: `/inventory/list` and `/inventory/search` render their results tables with no Fit column and the same column count as before. This is the test that catches a shared-table change leaking onto the pages that already use it. Depends on T013, T014, T019.

**Checkpoint**: The page loads, a search runs end to end and returns nothing — no fit rule
exists yet. The counters are already truthful. The existing list and search pages are proven
unchanged.

---

## Phase 3: User Story 1 — Orientation stops hiding stock (Priority: P1) 🎯 MVP

**Goal**: A rectangular request finds rectangular stock whatever order its dimensions were
recorded in, and finds larger stock that can yield it.

**Independent Test**: Record the same physical bar twice with its measurements in two different
field orders, search once for those measurements, and verify both records come back.

- [X] T021 [US1] Implement rule F1 — box into box — in `app/utils/fit.py` per [contracts/fit-rules.md §3](./contracts/fit-rules.md): sort both triples descending and compare componentwise. Comment that the sorted assignment is also the minimising orientation, so no permutation search is needed. Depends on T004, T005.
- [X] T022 [US1] Build the `Fit` result in `app/utils/fit.py` for a successful F1 match: `orientation`, `item_cross_section`, `requested_cross_section` and per-dimension `excess`, all exact `Decimal` subtraction — no area figure is exposed to the caller for display (fit-rules §6). `within_tolerance` is `False` and `tolerance_dimensions` empty until US4. Depends on T021.
- [X] T023 [US1] Add F1 tests to `tests/unit/test_fit.py`: every ordering of 0.5 × 3 × 4 against a record of 0.5 × 4 × 3 returns the identical verdict; a 0.75 × 3 × 4 request against a 0.5 × 3 × 4 item does not fit; a 1 × 6 × 12 item yields a 0.5 × 3 × 4 piece; an exactly-equal item fits (inclusive boundary, FR-012). Depends on T022.
- [X] T024 [US1] Serialize the `fit` object in the `POST /api/inventory/find-stock` response in `app/main/routes.py` per [contracts/find-stock-api.md](./contracts/find-stock-api.md), and render it in the Fit cell in `app/static/js/components/inventory-table.js` — item cross-section, requested cross-section, and the excess (FR-021, FR-022). Depends on T014, T022.
- [X] T025 [US1] Add the orientation e2e test to `tests/e2e/test_find_stock.py`: seed via `live_server.add_test_data` a bar recorded 0.5 × 4 × 3, search for 0.5 × 3 × 4 and for two other orderings, and assert the same result set each time. Wait with `expect(rows).to_have_count(n)` — pattern C, the rows are appended after the `fetch` resolves. Depends on T019, T024.
- [X] T026 [US1] Add the negative e2e assertion to `tests/e2e/test_find_stock.py`: an item too small in every ordering is absent. Establish the row count with `expect(...)` **before** reading the row set — a negative assertion against a table that has not loaded passes trivially. Depends on T025 (same file).

**Checkpoint**: The bug reported in issue #100 is fixed and shippable. Rectangular requests
against rectangular, square and angle stock work in every orientation.

---

## Phase 4: User Story 2 — A bigger piece of any shape is still stock (Priority: P1)

**Goal**: Requests and stock match across shapes — a round request finds square and rectangular
stock, and a rectangular request finds round stock.

**Independent Test**: Record only a square bar and a rectangular block of a material, search for
a round piece of that material that both can yield, and verify both are returned.

- [X] T027 [P] [US2] Accept the round request shape in `app/main/routes.py` and `app/utils/fit.py`: `diameter` and `length` instead of the three rectangular dimensions, validated by the same rules. Depends on T005, T011.
- [X] T028 [US2] Implement rule F2 — box into cylinder — in `app/utils/fit.py`: for each of the three choices of axial request dimension, `x ≤ h` and `y² + z² ≤ d²`. **Compare squares; never call `sqrt` and never introduce `float`** (D4, Principle III). Among fitting choices take the largest `y · z`. Depends on T021.
- [X] T029 [US2] Implement rule F3 — cylinder into box — in `app/utils/fit.py`: for each axis, that dimension `≥ L` and both others `≥ D`; among fitting axes take the smallest remaining product. Depends on T028 (same file).
- [X] T030 [US2] Implement rule F4 — cylinder into cylinder — in `app/utils/fit.py`, both orientations: upright (`D ≤ d` and `L ≤ h`) and crosswise (`D ≤ h` and `D² + L² ≤ d²`). Comment why crosswise uses `h × d` as its cross-section — the deliberate overstatement that ranks sawing a rod out of a plate below parting one off a bar. Depends on T029 (same file).
- [X] T031 [US2] Add F2/F3/F4 tests to `tests/unit/test_fit.py`, including every negative case the spec names: a Ø1.5" bar refuses a Ø2" request; a Ø2" bar refuses a 2" × 2" cross-section; a 0.5"-thick bar refuses a Ø2" round. Plus the positives: 3" square bar and 6" cube both yield a Ø2" × 2" round; a Ø4" bar yields a 1 × 2 × 3 box; a Ø6" × 0.25" disc yields a 0.2 × 1 × 5 bar through F2. Depends on T030.
- [X] T032 [US2] Add the round-request controls to `app/templates/inventory/find-stock.html` and the shape toggle to `app/static/js/inventory-find-stock.js` — choosing Round swaps the three rectangular inputs for diameter and length. Depends on T015, T016, T027.
- [X] T033 [US2] Add the cross-shape e2e test to `tests/e2e/test_find_stock.py`: seed a square bar and a rectangular block only, search for a round piece both can yield, assert both are returned. Depends on T026, T032 (same file).
- [X] T034 [US2] Add the hollow-exclusion e2e assertion to `tests/e2e/test_find_stock.py`: a tube large enough in its outside dimensions never appears in results, and the `skipped_hollow` counter accounts for it (FR-010, SC-006). Depends on T033 (same file).

**Checkpoint**: Both P1 stories done. The search answers "what can make this part" across every
solid shape in the inventory.

---

## Phase 5: User Story 3 — The closest fit is at the top (Priority: P2)

**Goal**: Results arrive ordered so the operator takes the first one and stops reading.

**Independent Test**: Record several items of one material that can all yield the same requested
piece, run one search, and verify the order runs from least material removed to most.

- [X] T035 [US3] Implement the sort key in `app/utils/fit.py` — terms 2, 3 and 4 of [contracts/fit-rules.md §4](./contracts/fit-rules.md): removed cross-section area, the envelope's axial extent, then `ja_id`. Term 1 arrives with US4. `PI` is used here and only here. Depends on T030.
- [X] T036 [US3] Apply the ordering in `InventoryService.find_stock()` in `app/mariadb_inventory_service.py` — sorted in Python, not in SQL (D5). Depends on T009, T035.
- [X] T037 [US3] Add the `case 'fit'` to `getSortValue()` in `app/static/js/components/inventory-table.js` and mark the Fit header sortable, so the column behaves like its neighbours (FR-029). Depends on T014, T024.
- [X] T038 [US3] Add ordering tests to `tests/unit/test_mariadb_inventory_service.py`: an exact match sorts first; a Ø2" bar 12" long outranks a Ø2.5" bar 2" long for a Ø2" × 2" request (D6 — this is the assertion that pins the interpretation of FR-019, so state that in a comment); two items tying on all three preceding terms come back in `ja_id` order, and the same search run twice returns the same order (FR-020). Depends on T036.
- [X] T039 [US3] Add the ordering e2e test to `tests/e2e/test_find_stock.py`: seed several items that all fit, assert the first row is the one with the least removed. Depends on T034 (same file).
- [X] T040 [US3] Add the FR-029 e2e assertion to `tests/e2e/test_find_stock.py`: results render in the server's order on arrival — not re-sorted by JA ID — and clicking another column header still sorts. This guards `setItems()` never gaining a sort. Depends on T039 (same file).

**Checkpoint**: The larger result sets the P1 stories produce are now navigable.

---

## Phase 6: User Story 4 — Nominal, within a tolerance set per dimension (Priority: P2)

**Goal**: Each requested dimension can carry its own tolerance; a blank tolerance is exact.

**Independent Test**: Record an item slightly short on one dimension and correct on the others,
search with a tolerance on that dimension alone, verify it is returned; remove the tolerance and
verify it is not.

- [X] T041 [US4] Implement the two-pass evaluation in `app/utils/fit.py` per [contracts/fit-rules.md §5](./contracts/fit-rules.md): nominal first, then effective. An item that fails both is not returned; one that passes only the second is `within_tolerance`. Depends on T030, T005.
- [X] T042 [US4] Implement tolerance attribution in `app/utils/fit.py`: re-run with each single tolerance restored to nominal and name every dimension whose restoration makes the fit fail, labelled through `taxonomy.field_label` so the operator sees `Diameter`, not `width` (FR-018). Depends on T041.
- [X] T043 [US4] Add term 1 to the sort key in `app/utils/fit.py` — exact fits before tolerance-only fits. Comment why: a tolerance-only match is stock *under* nominal, so it has the smaller cross-section and would otherwise sort to the top (D7). Depends on T035, T041.
- [X] T044 [US4] Add the per-dimension tolerance inputs to `app/templates/inventory/find-stock.html`, one beside each dimension, and carry them in the payload from `app/static/js/inventory-find-stock.js` as the `*_tolerance` keys. A blank field means exact and must send nothing rather than a zero-ish string (FR-015, FR-016). Depends on T032.
- [X] T045 [US4] Render the within-tolerance marker in the Fit cell in `app/static/js/components/inventory-table.js`, naming the load-bearing dimensions, so a tolerance-only match is distinguishable at a glance (FR-018). Depends on T024, T042.
- [X] T046 [US4] Add tolerance tests to `tests/unit/test_fit.py`: a 1.98"-long item fits a 2" request with a 0.02" tolerance on length and not without one; an item 1.98" long **and** 0.48" thick does not fit a 2" × 0.5" request carrying a tolerance on length only; the named dimension is the one that was load-bearing. Depends on T031, T042.
- [X] T047 [US4] Add the two tolerance 400 cases to `tests/unit/test_routes.py` — a negative tolerance, and one at least as large as the dimension it applies to — each naming the dimension (FR-017). Depends on T012, T041.
- [X] T048 [US4] Add the ordering-with-tolerance test to `tests/unit/test_mariadb_inventory_service.py`: an exact fit outranks a tolerance-only fit that removes less material. Depends on T038, T043.
- [X] T049 [US4] Add the tolerance e2e test to `tests/e2e/test_find_stock.py`: seed a slightly-short item, search without a tolerance and assert it is absent, add the tolerance on that dimension alone and assert it appears marked as within tolerance with the dimension named. Depends on T040 (same file).

**Checkpoint**: All four stories complete. The feature matches the spec.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T050 [P] Add a "Find Stock for a Part" section to `docs/user-manual.md` beside the advanced search section: what question it answers, how it differs from the advanced search, and what the counters mean.
- [X] T051 [P] Add a `find_stock_form` entry to `tests/e2e/screenshot_config.yaml`, modelled on the `search_form` entry (`:166`), with a `wait_for` naming a real element on the new page.
- [X] T052 Regenerate documentation screenshots — `venv/bin/nox -s screenshots_headless` then `venv/bin/nox -s screenshots_verify`. **Screenshot output churns on every run**: inspect `git diff --stat docs/images/screenshots/` and stage only the images this change actually alters. Depends on T050, T051.
- [X] T053 Run `venv/bin/nox -s tests` and confirm green, comparing against `/tmp/027-baseline-tests.log` from T001.
- [X] T054 Run the full e2e suite **detached** — `nohup env PATH=... venv/bin/nox -s e2e > /tmp/027-e2e.log 2>&1 &` — then poll. It takes about 13m 45s warm and will false-timeout on any 10-minute tool cap. Confirm the four existing search e2e files still pass unchanged (FR-026). Depends on T049.
- [X] T055 Confirm the working tree is clean after the test runs — `git status --short` — per Principle IV: a test session must not modify tracked files. Depends on T053, T054.
- [X] T056 Walk [quickstart.md](./quickstart.md) end to end against a running app: the four seeded items, the six checks, and the two-second expectation in SC-005. Depends on T054.
- [X] T057 [P] Run `venv/bin/nox -s lint` and clean up the **new** files only. Advisory, not a gate — do not reformat existing files, which destroys review signal (Development Workflow).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. **Blocks every story.**
- **US1 (Phase 3)**: depends on Foundational. No dependency on any other story.
- **US2 (Phase 4)**: depends on Foundational and on T021/T022 from US1 — F2, F3 and F4 share the `Fit` result construction F1 introduces.
- **US3 (Phase 5)**: depends on Foundational and on US2's rules existing, because the sort key must compute a cross-section for all four rules.
- **US4 (Phase 6)**: depends on Foundational and on the rules from US1 and US2; its sort term also depends on T035 from US3.
- **Polish (Phase 7)**: depends on every story that is being shipped.

### Story independence, honestly stated

These four stories are **incremental layers on one code path**, not four parallel tracks. Each
is independently *testable* and each is independently *shippable* — stopping after US1 leaves a
working search that fixes the reported bug — but they are not independently *implementable* in
any order. US2 extends the rule set US1 starts; US3 ranks whatever rules exist; US4 wraps the
whole evaluation. The dependency chain above reflects the real code, and pretending otherwise
would produce merge conflicts in `app/utils/fit.py` on the first day.

### Parallel Opportunities

Genuinely parallel work, by file:

- **Phase 2**: T013 (macro), T015 (template), T018 (nav) and T019 (page object) touch four different files and can proceed together, as can T003/T005 against T009's service skeleton.
- **Phase 4**: T027 (route/request shape) is independent of T028–T030 (the rules) until they meet in T031.
- **Phase 7**: T050, T051 and T057 are three different files.

Not parallel, despite appearances:

- **T006, T007, T008, T023, T031, T046** all write `tests/unit/test_fit.py`. Sequential.
- **T020, T025, T026, T033, T034, T039, T040, T049** all write `tests/e2e/test_find_stock.py`. Sequential.
- **T021, T028, T029, T030, T035, T041, T042, T043** all write `app/utils/fit.py`. Sequential.

---

## Parallel Example: Phase 2

```bash
# Four different files, no shared dependency:
Task: "Add show_fit_column to app/templates/inventory/_item_table.html"
Task: "Create app/templates/inventory/find-stock.html"
Task: "Add the nav entry to app/templates/base.html"
Task: "Create tests/e2e/pages/find_stock_page.py"
```

---

## Implementation Strategy

### MVP (Foundational + US1)

1. Phase 1 Setup — T001, T002.
2. Phase 2 Foundational — T003–T020. **Blocks everything.**
3. Phase 3 US1 — T021–T026.
4. **Stop and validate**: the search returns 0.5 × 4 × 3 for a 0.5 × 3 × 4 request. That is the
   whole of what issue #100 reports as broken, and it is shippable on its own.

### Incremental Delivery

| Increment | Adds | Ships |
|---|---|---|
| Foundational + US1 | orientation-free rectangular matching | the reported bug, fixed |
| + US2 | cross-shape yield, round requests | "what can make this part", fully |
| + US3 | ordering by material removed | a navigable result set |
| + US4 | per-dimension tolerance | nominal sizes, as machinists state them |

Each increment leaves the previous one working and adds no risk to the existing advanced search,
which is never modified.

---

## Notes

- **The two prohibitions that will bite**: no `float` and no `sqrt` anywhere in the geometry
  (compare squares — D4); and no `wait_for_timeout` or `time.sleep` in the e2e test (wait on
  `expect(...)` — Principle IV). Both are constitution-level, not style.
- **Read `setItems()` before touching `inventory-table.js`.** It calls `render()` and never
  `sortBy()` (`:83-88`), which is the only reason the server's ordering survives first render.
  T040 exists to catch a future change to that.
- **`search_active_items` is not to be modified.** FR-026, and four existing e2e files depend
  on it.
- Commit after each task or logical group. The feature branch is `issues/100`; non-trivial code
  merges via pull request.
