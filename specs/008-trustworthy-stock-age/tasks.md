# Tasks: Trustworthy Stock Age

**Feature**: `specs/008-trustworthy-stock-age/` | **Branch**: `issues/59`

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]** — parallelizable: a different file from every other task running with it, and no dependency on incomplete work.
- **[US1] / [US2] / [US3]** — the user story from `spec.md` the task serves. Setup, Foundational and Polish tasks carry no story label.

## Path Conventions

Repository root is `/home/jantman/scratch/rm_me/workshop-inventory-tracking`. Paths below are relative to it. Source the virtualenv (`venv/`) before running anything, and run tests through `nox`, never `pytest` directly.

**Tests are not optional here.** Constitution IV requires that a change altering behaviour lands with tests covering that behaviour. Every story below therefore carries its tests as ordinary tasks, not as an opt-in.

**Two FR namespaces.** Code in `app/` already cites feature 001's FR numbers (FR-024, FR-025, FR-029) in docstrings and comments. This feature has its own FR-001…FR-015. Where a new comment cites one, qualify it — `008 FR-008` — so the next reader is not sent to the wrong spec.

---

## Phase 1: Setup

**Purpose**: confirm the ground the change stands on before touching anything.

- [ ] T001 Confirm the current Alembic head is `b1a0c0d10009` by checking `down_revision` across `migrations/versions/*.py`; the new revision in T008 must chain from whatever this reports, not from what the plan assumed
- [ ] T002 Run `nox -s tests` and record it green, so that any failure after this point belongs to this feature

**Checkpoint**: baseline established.

---

## Phase 2: Foundational (Blocking Prerequisites)

**None.** This is a finding, not an omission.

User Story 1 is a deleted line in `app/catalog_service.py` and needs no schema change, no new column and no new property — it can ship on its own, ahead of everything else. User Story 2 owns the migration and the new column outright; nothing else depends on them. There is no shared scaffolding for the two to wait on, so introducing a foundational phase would only serialize work that is genuinely independent.

**Checkpoint**: proceed directly to Phase 3.

---

## Phase 3: User Story 1 - The reorder list stops claiming a count nobody made (Priority: P1) 🎯 MVP

**Goal**: receiving a purchase adds the received quantity to a tracked count and leaves the count's age exactly where it was, so the screen stops reporting a verification that never happened.

**Independent test**: seed a product with a tracked count, backdate `quantity_updated_at` by three months, receive an outstanding purchase against it, and confirm the count rose by the received quantity while the stored timestamp is byte-for-byte unchanged.

**Why it stands alone**: no schema change and no display change. The age line already exists; this makes it tell the truth.

### Tests for User Story 1

- [ ] T003 [US1] Add a `TestReceivingDoesNotVerifyACount` class to `tests/unit/test_stock_status.py` with a module-level helper that backdates a product's `quantity_updated_at` through `service.Session()`, covering: the count rises by the received quantity (FR-007); the stored timestamp is **unchanged** — assert equality against the seeded value, not `>=` or "older than now", because the weaker assertion passes against a bug that moves it by a second (FR-008, SC-001); receiving against a product with `quantity IS NULL` leaves both `quantity` and `quantity_updated_at` NULL (FR-009); a purchase with no quantity changes neither; and receiving an already-received purchase changes neither
- [ ] T004 [P] [US1] Add `test_receiving_does_not_reset_a_counted_age` to a new `tests/e2e/test_stock_age.py`: seed a product and an outstanding purchase through `CatalogService(live_server.storage)`, backdate the count through `sessionmaker(bind=live_server.engine)`, receive through the reorder list's **Receive** button, and `expect(page.locator("#quantity-age"))` to still read the aged text while `#quantity-value` shows the increased count

### Implementation for User Story 1

- [ ] T005 [US1] In `app/catalog_service.py`, delete the `product.quantity_updated_at = datetime.now()` line inside `receive_purchase`'s `if not already_received` block (currently line 1319), keeping the increment above it; rewrite the surrounding comment and the method docstring's receiving paragraph to say that the count moves and its age does not, citing `008 FR-007`/`008 FR-008`
- [ ] T006 [P] [US1] In `app/database.py`, update the `quantity_age` property docstring: the value now means "how long ago an operator counted", not "how long ago the number was written", and the difference is the point of the change — say so, so the deleted line is not restored later as a bug fix

**Checkpoint**: `nox -s tests` and the new E2E test pass. Receiving is honest. This is a shippable increment on its own.

---

## Phase 4: User Story 2 - A hand-set flag shows how old it is (Priority: P2)

**Goal**: a manual low/out flag records when it was set and displays that age wherever the flag appears, in the same words a count's age uses.

**Independent test**: flag one product now, seed another as flagged two years ago and a third as flagged with no recorded date, then open the reorder list and read three distinct ages — *just now*, *2 years ago*, *at an unknown time* — without opening any of them.

**Depends on**: nothing in Phase 3. It can be built and shipped independently; T012's flag-date clearing touches the same method as T005, so if both phases are in flight, sequence those two edits.

### Schema and model

- [ ] T007 [US2] Create `migrations/versions/b1a0c0d10010_add_stock_status_updated_at.py` chaining from the head confirmed in T001: `upgrade` adds `products.stock_status_updated_at` as a nullable `sa.DateTime()` with no server default and **no backfill**; `downgrade` drops it. Document in the revision docstring that the reverse loses only flag ages, and that not backfilling from `last_modified` is deliberate (008 FR-005, SC-006)
- [ ] T008 [US2] In `app/database.py`, add the `stock_status_updated_at` column to `Product` beside `stock_status`, matching the migration's type and nullability exactly — the unit suite builds its schema with `create_all` and never runs the migration, so drift between the two is invisible to `nox -s tests`. Add no CHECK constraint; `research.md` records why
- [ ] T009 [US2] In `app/database.py`, add the `stock_status_age` property as a line-for-line mirror of `quantity_age` — `None` when there is no flag and `None` when there is a flag with no recorded date — and add `stock_status_updated_at` to `to_dict()` next to `stock_status`, ISO-formatted or `None`, per `contracts/product-json.md`

### Service rules

- [ ] T010 [US2] In `app/catalog_service.py`, make `set_stock_status` write `stock_status_updated_at = datetime.now()` whenever a flag value is stored — including when the stored value equals the incoming one, which is what makes a re-assertion produce an `UPDATE` at all (008 FR-002) — and write `None` to it when the flag is cleared (008 FR-003); extend the docstring to state both
- [ ] T011 [US2] In `app/catalog_service.py`, clear `stock_status_updated_at` alongside `stock_status` in `receive_purchase`, inside the existing flag-clearing branch and its log line (008 FR-006)
- [ ] T012 [US2] Confirm `update_product`'s `editable` set in `app/catalog_service.py` still excludes `stock_status`, `stock_status_updated_at`, `quantity` and `quantity_updated_at`, and do not add any of them; SC-003 is checkable only because these fields have exactly four writers

### Presentation

- [ ] T013 [P] [US2] In `app/product/routes.py`, give `relative_age` an optional second parameter — `def relative_age(age, unknown: str = 'never counted') -> str` — returned in place of the hardcoded string in the `None` branch, leaving all existing call sites unchanged; note in the docstring that a count and a flag share this function so their wording cannot drift (008 FR-012)
- [ ] T014 [P] [US2] In `app/templates/product/detail.html`, add a muted line with `id="flag-age"` under the three flag buttons, rendered only inside `{% if product.stock_status %}`, reading `Flagged {{ product.stock_status }} {{ product.stock_status_age | relative_age('at an unknown time') }}`
- [ ] T015 [P] [US2] In `app/templates/product/reorder.html`, add a muted `<div class="flag-age">` under the existing `reason-manual` badge, inside the same `{% if entry.is_manually_low %}` guard, rendering `{{ product.stock_status_age | relative_age('at an unknown time') }}`

### Tests for User Story 2

- [ ] T016 [US2] Extend `tests/unit/test_stock_status.py`: setting a flag records the moment (FR-001); setting a flag to the value it already holds moves the stored date forward, verified by backdating first (FR-002); clearing writes `None` to both (FR-003); `stock_status_age` is `None` with no flag and `None` with a flag and no date (FR-005); receiving clears the flag and its date together (FR-006); `to_dict()` carries the ISO field; and `relative_age(None)` still returns `never counted` while `relative_age(None, 'at an unknown time')` returns the override (FR-012)
- [ ] T017 [P] [US2] Extend `tests/e2e/test_stock_age.py`: flagging from the detail page leaves `#flag-age` reading *Flagged low just now*, reusing `test_reorder_view.py`'s `wait_for_stock_flag` pattern for the post-click reload; a seeded flag with a `NULL` date reads *at an unknown time*; clearing the flag makes `#flag-age` absent rather than empty; and a received purchase leaves neither flag nor flag age
- [ ] T018 [P] [US2] Extend `tests/e2e/test_reorder_view.py` with a test seeding two flagged products at different backdated times and asserting their `.flag-age` cells, scoped by each row's `data-product-id`, read different ages (SC-004)
- [ ] T019 [US2] Exercise `b1a0c0d10010` up, down and up again against a **disposable MariaDB container** — never the database named in `.env`, since neither suite runs migrations — and confirm after the upgrade that every `stock_status_updated_at` is `NULL`

**Checkpoint**: both suites pass, and the reorder list distinguishes a flag set today from one set two years ago.

---

## Phase 5: User Story 3 - Adjusting a count at the shelf still counts as counting (Priority: P3)

**Goal**: prove the boundary US1 draws is the right one — an operator's own adjustment still resets the count's age, and only receiving stopped doing so.

**Independent test**: press the `−` button on a product whose count was last taken months ago and confirm the age line resets to *just now*.

**No production code.** This story is entirely tests. That is intentional: without them, "receiving must not refresh the age" is one careless edit away from becoming "nothing refreshes the age", which would silently break the most common way a count is kept honest.

### Tests for User Story 3

- [ ] T020 [US3] Extend `tests/unit/test_stock_status.py`: a typed count stamps the age (FR-010); `set_quantity(None)` clears the count, the age and the threshold, and setting a count afterwards writes a fresh age carrying nothing over (FR-011); and `create_product(quantity=...)` stamps the age, since creating a product with a count is an operator entering one
- [ ] T021 [US3] Extend `tests/e2e/test_stock_age.py`: seed a product with a backdated count, press `#quantity-increment` on the detail page, and `expect(page.locator("#quantity-age"))` to read *counted just now* after the reload — the `+`/`−` buttons reach `PATCH /api/products/<id>/quantity` and must not become a separate path

**Checkpoint**: the distinction the feature rests on is pinned by tests in both suites.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T022 [P] Update `docs/user-manual.md`: the stock section around line 694 gains the flag's age beside the count's, and the sentence at line 708 ("Receiving an order clears both kinds of low") gains what receiving now leaves alone — the count's age. Add a short note that flags set before this upgrade have no recorded age and will read *at an unknown time* until flagged again
- [ ] T023 [P] Update `docs/product-functionality-gap.md`: strike through the two "Reordering and stock" bullets and mark them *Built — feature 008*, matching how the Order capture section records feature 006
- [ ] T024 Run `nox -s tests` and `nox -s e2e` (allow a 15-minute tool timeout) and confirm both pass and the working tree is left clean
- [ ] T025 Work through the four hand-checks in `quickstart.md`, in particular the legacy-row check against a copy of the real database — every product flagged before today reading *at an unknown time* is correct behaviour and the single most likely thing to be reported as a bug

**Not a task: screenshots.** No committed screenshot shows a product page — `tests/e2e/screenshot_config.yaml` covers the metal-stock screens only — so regenerating would rewrite eleven unrelated PNGs with rasterization noise. The deviation and its reasoning are recorded in `plan.md`; the CI reminder that fires on `app/templates/**` is informational (issue #77) and blocks nothing.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** → everything. T001's answer determines the migration's `down_revision`.
- **Phase 2 (Foundational)** → empty; nothing blocks.
- **Phase 3 (US1)** and **Phase 4 (US2)** are independent of each other and may be built in either order or in parallel, with one exception: T005 and T011 both edit `receive_purchase`, so sequence those two.
- **Phase 5 (US3)** is best done after Phase 3, since it exists to guard the boundary Phase 3 draws — but its tests pass before and after, so it does not block.
- **Phase 6 (Polish)** → after the stories whose behaviour it documents.

### Within User Story 2

```
T007 (migration) ─┐
T008 (column) ────┴─→ T009 (property, to_dict) ─→ T016 (unit tests)
                                                 ↘
T010, T011, T012 (service) ──────────────────────→ T017, T018 (E2E)
T013 (filter) ─→ T014, T015 (templates) ─────────↗
T019 (migration up/down) — independent of the rest; do it before merging
```

T014 and T015 need T009's property and T013's parameter to exist at render time. Editing them earlier is harmless; running the E2E tests before those land is not.

### Parallel opportunities

- **T004 with T003** — different files (`tests/e2e/test_stock_age.py`, `tests/unit/test_stock_status.py`).
- **T006 with T005** — different files (`app/database.py`, `app/catalog_service.py`).
- **T013, T014, T015** — three different files, once T009 exists.
- **T017 with T018** — different E2E files.
- **T022 with T023** — different documents.

Everything touching `tests/unit/test_stock_status.py` (T003, T016, T020) is one file and runs sequentially, as does everything touching `app/catalog_service.py` (T005, T010, T011, T012).

---

## Implementation Strategy

### MVP: User Story 1 alone

T001–T006. Six tasks, one deleted line of production code, two docstrings and two tests. It removes the only place the application currently states something untrue, needs no migration, and can be merged without any of the rest. If the feature were cut short here it would still have paid for itself.

### Incremental delivery

1. **US1** — receiving stops claiming a verification. Ship.
2. **US2** — the flag gets an age. This is the larger half: the migration, the column, the property, the service rules and both templates. Ship.
3. **US3** — pin the boundary. Tests only.
4. **Polish** — the two documents, the full suites, the hand-checks.

### The two things most likely to go wrong

- **An FR-008 test that asserts too weakly.** `assert product.quantity_updated_at >= seeded` passes against the exact bug being removed. Assert equality with the seeded value.
- **Model/migration drift.** `nox -s tests` builds its schema from the model with `create_all` and never runs Alembic, so a column that differs between `app/database.py` and `b1a0c0d10010` passes the unit suite and fails on the real database. T019 is the only thing that catches it.
