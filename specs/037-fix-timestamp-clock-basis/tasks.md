---

description: "Task list for feature 037 — One Clock for Recorded Timestamps"
---

# Tasks: One Clock for Recorded Timestamps

**Input**: Design documents from `/specs/037-fix-timestamp-clock-basis/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/clock.md](./contracts/clock.md)

**Tests**: Required, not optional. Constitution IV — "changes that alter behavior MUST land with
tests covering that behavior". The behavior here is invisible on every screen, so the tests are
the only thing that can tell you the change worked.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2, US3 — maps to the user stories in [spec.md](./spec.md)
- Every task names its file paths

## Path Conventions

Single Flask application at the repository root: `app/` for source, `tests/unit/` and
`tests/e2e/` for tests. All paths below are repository-relative.

---

## A note on the phase order

**Phases 3 and 4 are one atomic change. Do not stop between them.**

Phase 3 (US1) moves the write side to UTC. Phase 4 (US2) moves the read side to match. Land the
first without the second and every product on the site reads "counted just now", because a count
written in UTC is four hours ahead of a local `datetime.now()` and
`app/product/routes.py:1131` renders a negative age as `'just now'`. That guard exists to absorb
clock skew and it will absorb this instead — silently, which is the whole character of this bug.

They are split into two phases because they answer two different user stories and need two
different tests, not because they can ship apart. One commit, one PR.

Phase 5 (US3) **is** independent: it renames five call sites to say what they already do, with no
behavior change, and can land before or after the rest.

---

## Phase 1: Setup

No setup. No new dependency, no new configuration, no scaffolding — the feature is standard-library
`datetime` and one new module. This section is here to record that the absence is deliberate.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the clock everything else calls, and the test fixture that makes the defect visible.

**⚠️ No story work can begin until this phase is complete.**

- [ ] T001 [P] Create `app/utils/clock.py` with exactly two public functions and no other surface, per [contracts/clock.md](./contracts/clock.md): `utc_now() -> datetime` returning `datetime.now(timezone.utc).replace(tzinfo=None)`, and `local_now() -> datetime` returning `datetime.now()`. Both return **naive** datetimes — see research.md R2 for why aware is wrong here, and `app/models.py:1263` (`_naive`) for what this codebase already paid for mixing the two. Module docstring must state the partition the whole feature rests on: `utc_now()` for an instant the application recorded, `local_now()` for a day the operator stated. Type hints on both (Constitution, Technology Constraints). **Do not add** a parameter, a configuration read, an injectable clock, or a freeze hook — tests patch the module attribute, which needs no production affordance (plan.md, Post-Design Constitution Re-check)
- [ ] T002 [P] Create `tests/unit/test_clock_basis.py` with a module docstring explaining why a forced timezone is load-bearing (research.md R9: SQLite's `CURRENT_TIMESTAMP` is UTC, so on a runner set to UTC the naive version of every test below passes against the unfixed code), a `forced_timezone` fixture that sets `os.environ['TZ'] = 'America/New_York'`, calls `time.tzset()`, yields, then **restores the previous value and calls `tzset()` again** in teardown, and tests for the clock module itself: `utc_now()` and `local_now()` both return `tzinfo is None`, and under the fixture they differ by the zone's offset. Mark the tests `@pytest.mark.unit` if that is the file convention in `tests/unit/`

**Checkpoint**: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` green. The clock exists and nothing calls it yet.

---

## Phase 3: User Story 1 — Two recorded times on one record agree (Priority: P1) 🎯 MVP

**Goal**: every timestamp the application records for itself lands on naive UTC, produced in
Python, whatever wrote it.

**Independent Test**: create a product and count it in the same minute with `TZ` forced to a
non-UTC zone; every recorded timestamp on the row falls within a minute of every other. Today the
gap is 3:59:59 — verified live, see quickstart.md §1.

### Tests for User Story 1

These four go in `tests/unit/test_clock_basis.py` and are written before the implementation below.

- [ ] T003 [US1] Add the reported-bug test: under `forced_timezone`, build a `CatalogService` on the `test_storage` fixture, `create_product(description=..., quantity=1)`, read it back with `get_product`, and assert `abs(date_added - quantity_updated_at) < timedelta(minutes=1)` and the same for `last_modified` and `stock_status_updated_at` where set (FR-001, FR-004, SC-001). This is issue #134 as an assertion; it must fail with a ~4-hour gap before Phase 3's implementation
- [ ] T004 [US1] Add the structural default test: walk every mapped class on `app.database.Base` and every `DateTime` column on it, and assert that any column carrying a `default` or `onupdate` holds a **Python callable** that is `app.utils.clock.utc_now` — not a SQL clause element. Assert the set of such columns matches the thirteen in [data-model.md](./data-model.md) — the fifteen recorded columns less `products.quantity_updated_at` and `products.stock_status_updated_at`, which are nullable and carry no default — so a new one cannot appear unnoticed. **This is the only test that can see the defaults move into Python** (research.md R3, R9): under SQLite, `func.now()` and `utc_now()` both produce UTC, so no value-based test can tell them apart. It is also what catches a fourteenth column added on `func.now()` later
- [ ] T005 [US1] Add the explicit-write test: patch `app.catalog_service.utc_now` to return a fixed sentinel instant, call `set_quantity` and `set_stock_status`, and assert the stored `quantity_updated_at` and `stock_status_updated_at` equal the sentinel exactly (INV-1, FR-012). Patch the **module-global name in `app.catalog_service`**, not `app.utils.clock.utc_now` — a `from … import` binding is resolved at call time inside the function, which is what makes this patchable, while a `Column(default=…)` argument is bound at class-definition time and is not. That asymmetry is why T004 exists as a separate, structural test
- [ ] T006 [US1] Add the second-table test: under `forced_timezone`, add a material through `MariaDBMaterialsAdminService` (`app/mariadb_materials_admin_service.py`) and assert its `date_added` and `last_modified` are within a minute of a `utc_now()` reading. This is the unreported half of the defect (research.md R1) — `material_taxonomy` fails today for exactly the same reason `products` does
- [ ] T007 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm **T003, T004 and T006 fail** against current code, recording which failure each gives. T005 may already pass — it asserts the mechanism, not the basis. If T003 *passes*, the `forced_timezone` fixture is not taking effect and T002 is wrong

### Implementation for User Story 1

- [ ] T008 [US1] In `app/database.py`, add `from .utils.clock import utc_now` and replace every `default=func.now()` with `default=utc_now` and every `onupdate=func.now()` with `onupdate=utc_now`, at lines 78, 79, 638, 639, 714, 715, 776, 870, 871, 1119, 1120, 1207, 1377 — the thirteen defaulted columns inventoried in [data-model.md](./data-model.md). **No `()` on the callable**: SQLAlchemy calls it per insert; `default=utc_now()` would freeze one timestamp at import. Leave `func` imported if other code in the file uses it. **Do not touch** `purchase_date` (:65), `order_date` (:1061) or `received_date` (:1063) — those are calendar days and carry no default
- [ ] T009 [P] [US1] In `app/catalog_service.py`, replace `datetime.now()` with `utc_now()` at **:223, :445 and :499 only**, and add the import. **Do not touch :1151, :1620 or :2072** — those default a calendar day and belong to Phase 5 (US3); converting them shifts an evening order onto the next day, which is the one way this feature can introduce a visible bug (research.md R5)
- [ ] T010 [P] [US1] In `app/mariadb_materials_admin_service.py`, replace `datetime.now()` with `utc_now()` at :180, :181, :250 and :354, and add the import. These four are the `material_taxonomy` defect; T006 is their test
- [ ] T011 [P] [US1] In `app/mariadb_inventory_service.py`, replace `datetime.now(timezone.utc)` with `utc_now()` at :603, :637, :638, :1133 and :1166, **and the stray `func.now()` assignment at :953** — that one is a SQL expression assigned to an instance attribute, so it takes the database server's clock on flush, which is what FR-003 removes. Drop the now-unused `timezone` import if nothing else in the file uses it
- [ ] T012 [P] [US1] In `app/mariadb_storage.py`, replace `datetime.now(timezone.utc)` with `utc_now()` at :430 and :442, and drop `timezone` from the imports if it becomes unused
- [ ] T013 [P] [US1] In `app/photo_service.py`, replace `datetime.utcnow()` with `utc_now()` at :118, :119, :133, :423 and :873. Same basis, but `utcnow()` is deprecated on Python 3.13 — this retires it as a side effect rather than as a separate cleanup
- [ ] T014 [P] [US1] In `app/main/routes.py`, **delete** the four writes at :742, :2403, :2472 and :2473 rather than converting them. `add_item` never copies `date_added`/`last_modified` onto the row and `update_item` overwrites `last_modified` at `app/mariadb_inventory_service.py:953`, so all four record nothing (research.md R1). Keep the surrounding `updated_item.date_added = item.date_added` at :741 — that one preserves the original creation time across an edit and is load-bearing. Leave the comment at :740 accurate after the deletion, and keep the `# Set timestamps` comment out of the file with them. `_parse_item_from_form` builds the **ORM** `InventoryItem` and carries a function-local `from datetime import datetime` at :2423 whose only users are :2472 and :2473 — **remove that local import too**. Check the module-level `datetime` import separately; other functions in the file still use it
- [ ] T015 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm T003–T006 now pass

**Checkpoint**: recorded timestamps agree. **Ages are now broken** — every count reads "just now"
until Phase 4 lands. Do not commit here.

---

## Phase 4: User Story 2 — Stock ages keep telling the truth (Priority: P2)

**Goal**: the read side moves with the write side, so "counted 3 hours ago" still means three
hours.

**Independent Test**: seed `quantity_updated_at` three hours back on the application clock with
`TZ` forced non-UTC, render the product page, and read "3 hours ago" rather than "just now".

### Tests for User Story 2

- [ ] T016 [US2] Add to `tests/unit/test_clock_basis.py`: under `forced_timezone`, seed `quantity_updated_at = utc_now() - timedelta(hours=3)` directly through a session (the `backdate` helper at `tests/unit/test_stock_status.py:28` is the established pattern and its docstring explains why the service cannot produce a backdated age), then assert `product.quantity_age` is within a minute of three hours (FR-007, INV-4). Add the mirror assertion for `stock_status_age`
- [ ] T017 [US2] Run the unit suite and confirm T016 **fails after Phase 3** — it should report an age near seven hours, or a negative one, because the write side has moved and the read side has not. A pass here means Phase 3 is incomplete

### Implementation for User Story 2

- [ ] T018 [US2] In `app/database.py`, change `datetime.now()` to `utc_now()` at :967 (`quantity_age`) and :983 (`stock_status_age`). These are the only two places an age is computed. Leave both double-`None` guards and both docstrings alone — including the note that receiving a purchase deliberately does not touch `quantity_updated_at` (008 FR-008). Drop the `datetime` import from the file only if nothing else uses it
- [ ] T019 [P] [US2] In `tests/e2e/test_stock_age.py`, retarget `days_ago()` at :26 onto `utc_now()` and update its one-line docstring to say which clock it seeds. The assertions need no change — the ages under test are 100 and 400 days, nowhere near a four-hour rendering boundary — but a seed on the local clock is the same defect this feature removes, and leaving it writes the bug into the suite as the expected shape (research.md R10)
- [ ] T020 [P] [US2] In `tests/e2e/test_reorder_view.py`, retarget the two `datetime.now() - timedelta(...)` seeds at :236 and :239 onto `utc_now()`. Same reasoning as T019; the ages are 9 and 800 days
- [ ] T021 [US2] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green, T016 included

**Checkpoint**: US1 and US2 together are the smallest correct increment. This is the commit boundary.

---

## Phase 5: User Story 3 — Dates the operator states keep the operator's day (Priority: P3)

**Goal**: the five calendar-day defaults say `local_now()`, so a later sweep cannot convert them
by mistake.

**Independent Test**: patch `local_now()` to a fixed 21:00 instant, capture an order with no order
date, and confirm the stored `order_date` is that day rather than the next one.

**No behavior changes in this phase.** `local_now()` returns exactly what `datetime.now()` returns.
The value is that after Phase 3 a bare `datetime.now()` in a service reads as a mistake, and these
five need to say they are not one (research.md R5).

### Tests for User Story 3

- [ ] T022 [P] [US3] Add to `tests/unit/test_clock_basis.py`: patch `app.catalog_service.local_now` to a fixed instant late in the local evening, call the order-capture path that defaults `order_date` (`app/catalog_service.py:1151`) with no order date supplied, and assert the stored `order_date` is that evening's **local** calendar day at midnight (FR-008, INV-3). Patch rather than testing against the real clock — an assertion that only fails after 20:00 is not a test. Add the mirror for `received_date` (`app/catalog_service.py:1620`)

### Implementation for User Story 3

- [ ] T023 [US3] In `app/catalog_service.py`, replace `datetime.now()` with `local_now()` at :1151, :1620 and :2072, and extend the import added in T009. Keep `.replace(hour=0, minute=0, second=0, microsecond=0)` at :1151 exactly as it is — that is what makes the value a day rather than an instant. The `now` at :2072 feeds `_resolve_arrival_date` and is compared against an operator-stated `order_date`, so it must stay on the operator's calendar
- [ ] T024 [P] [US3] In `app/models.py:1438`, replace `datetime.now()` with `local_now()` in `(today or datetime.now()).year`. This supplies the year for a bare "14 Mar" read off a vendor page; it is the year the operator is in. Import from `.utils.clock`
- [ ] T025 [US3] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T026 Run `grep -rn "datetime\.now()\|datetime\.utcnow()\|datetime\.now(timezone\.utc)" app/` and confirm the only survivors are the seven sites research.md R7 puts out of scope — `app/logging_config.py:274,336`, `app/export_service.py:457`, `app/export_schemas.py:211,220,225`, `app/main/routes.py:1128` — plus the two inside `app/utils/clock.py` itself. Anything else is a site the sweep missed
- [ ] T027 Confirm the diff adds no file under `migrations/versions/` and changes no existing one. `default=` is client-side in SQLAlchemy, so this feature emits no DDL (research.md R3); a migration appearing here means someone tried to drop the `server_default`s, which R4 decided against
- [ ] T028 Confirm the diff touches nothing under `app/templates/` or `app/static/`. It should not — no markup, CSS or JavaScript is involved — and if it does, the screenshot gate applies and `nox -s screenshots` becomes mandatory (Constitution, Development Workflow). No user-manual change either: nothing the operator does changes
- [ ] T029 Add a short **Timestamps** note to `_bmad-output/project-context.md` recording the convention: recorded instants come from `app.utils.clock.utc_now()` and are naive UTC; days the operator states come from `local_now()`; a bare `datetime.now()` in a service is a bug outside the logging and report sites. This is the only thing that keeps the next feature from reintroducing the defect
- [ ] T030 Re-run quickstart.md §1 against the finished code and confirm the gap is under a second, with `TZ=America/New_York` forced. It was 3:59:59 before
- [ ] T031 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` **detached** (`nohup` + poll — a foreground run reports a false timeout at 10 minutes on a suite that takes about 13m 45s). Two groups matter more than the rest: the **active-status and history** tests, because `inventory_items.date_added` selects the current history row and this feature is under Constitution VI whether or not it looks like it (research.md R8); and `tests/e2e/test_stock_age.py` plus `tests/e2e/test_reorder_view.py`, whose seeds T019 and T020 retargeted
- [ ] T032 Run `git status --short` after the e2e session and confirm the working tree is clean. Anything under `docs/images/screenshots/` means screenshot tests were selected and the run is wrong (Constitution IV)
- [ ] T033 Walk quickstart.md §3 by hand against a running instance: the four `products` timestamps within seconds of each other on a product created after the fix; a product page whose ages read in hours rather than "just now"; and — **only observable after 20:00 local** — an order captured with no date typed showing today's day on the order listing, not tomorrow's

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 2 (Foundational)** blocks everything. `utc_now()` has to exist before anything calls it.
- **Phase 3 (US1)** depends on Phase 2 only.
- **Phase 4 (US2)** depends on Phase 3 and **must land in the same commit** — see the note at the top. T017 is written to fail if Phase 3 is incomplete, which also means it fails if you run it before Phase 3.
- **Phase 5 (US3)** depends on Phase 2 for the import and on T009 for the import line in `app/catalog_service.py`. Otherwise independent of Phases 3 and 4; it can land first if that is more convenient.
- **Phase 6 (Polish)** depends on all of the above.

### Story independence

US1 and US2 are **not** independently shippable, and the plan says so rather than pretending
otherwise: the write side and the read side of the same subtraction have to move together. They
are separate phases because they are separate user stories with separate tests, not separate
releases.

US3 is genuinely independent — a rename with no behavior change.

### Within each phase

Test tasks come before implementation tasks, and the "confirm it fails" tasks (T007, T017) are
load-bearing: a regression test that has never been seen red is not known to test anything.
Research R9 exists because the obvious version of T003 passes against the bug on a UTC runner.

### Parallel opportunities

- **Phase 2**: T001 and T002 are different files — both at once.
- **Phase 3 implementation**: T009–T014 touch six different modules with no ordering between them. T008 is not marked `[P]` because T004 asserts against it and it is the file every other task imports from; do it first.
- **Phase 4**: T019 and T020 are different test files — both at once. T018 is alone in `app/database.py`.
- **Phase 5**: T022 and T024 are different files. T023 must follow T009 (same file, same import line).
- **Tests within `tests/unit/test_clock_basis.py`** (T003–T006, T016, T022) are the same file and are **not** parallel with each other.

```bash
# Phase 3, the six module sweeps at once:
#   T009 app/catalog_service.py
#   T010 app/mariadb_materials_admin_service.py
#   T011 app/mariadb_inventory_service.py
#   T012 app/mariadb_storage.py
#   T013 app/photo_service.py
#   T014 app/main/routes.py
```

---

## Implementation Strategy

### MVP (Phases 2 + 3 + 4)

The smallest thing that is correct and shippable. It fixes issue #134 on both tables, moves the
ages with it, and leaves the calendar dates alone. Phases 3 and 4 are one commit.

### Incremental delivery

Phase 5 can follow separately if the diff is getting long — it changes no behavior. Phase 6 is
verification and must not be skipped: T026 is the only thing that proves the sweep was complete,
and T031 is the Constitution VI gate.

---

## Notes

- **The bug is on two tables.** `material_taxonomy` was not in the issue and fails for the same
  reason `products` does. T006 and T010 are that half.
- **Four writes get deleted, not fixed.** `app/main/routes.py:742,2403,2472,2473` record nothing
  today (research.md R1). Converting them would preserve a misleading pattern.
- **Expect the ages on old rows to jump ~4 hours once, on deploy.** Rows written before the fix
  hold a local value now read against a UTC clock, so they report older than they are, bounded by
  the UTC offset. This is accepted and not correctable — the write-time offset was never recorded
  and a daylight-saving boundary makes it ambiguous (research.md R6). It is in quickstart.md so it
  reads as expected rather than as a new defect.
- **No new e2e test.** Everything this feature asserts is assertable in the sub-second unit suite,
  and SC-004 is already covered by `test_receiving_does_not_reset_a_counted_age`. The suite is at
  602 tests and 13m 45s; adding to it needs a reason this feature does not have.
