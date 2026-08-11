---

description: "Task list for Round Plate Dimensions"
---

# Tasks: Round Plate Dimensions

**Input**: Design documents from `specs/012-round-plate-dimensions/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/dimension-rules.md](./contracts/dimension-rules.md),
[quickstart.md](./quickstart.md)

**Tests**: included, and not optional here. Constitution Principle IV: "Changes that alter
behavior MUST land with tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST
pass before a change is merged." Every phase below ends by running them.

**Organization**: grouped by user story so each is independently completable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1, US2, US3, mapping to the user stories in [spec.md](./spec.md)
- Every task names the exact file it touches

## Before you start

- `source venv/bin/activate`, and put pyenv's 3.13 ahead of the system 3.14 on `PATH` or every
  nox session fails at creation.
- **`nox -s e2e` outlasts the Bash tool's 10-minute clamp. Run it in the background** and
  collect the result. The constitution asks for a 15-minute allowance; the suite takes ~8m15s
  warm.
- `nox -s lint` is red at baseline on pre-existing flake8 E501s. It is advisory, not a gate.
  Do not read its failures as yours and do not mass-reformat to clear them.

---

## Phase 1: Setup

**Purpose**: know what green looks like before changing anything, and confirm the design still
matches the code.

- [X] T001 Establish the baseline: run `nox -s tests`, and `nox -s e2e` in the background, and record any failure that already exists. This suite has a documented history of flakes, and a pre-existing red is not yours to own
- [X] T002 [P] Re-read the three rule statements side by side — `app/taxonomy.py:32-75`, `app/database.py:210-236`, `app/static/js/inventory-add.js:18-46` — and confirm the table in [data-model.md](./data-model.md) §2 still matches what is there. If it has drifted, correct the table before writing code from it

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the one authoritative rules table. Every user story reads from it.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

- [X] T003 Write `tests/unit/test_taxonomy.py` (new file — this module has never had a test) covering: Plate+Round and Sheet+Round require width and thickness and **not** length; Plate+Rectangular, Plate+Square and Sheet+Rectangular still require all three; Threaded Rod+Round does **not** require width; Bar+Round requires length and width; Channel yields no requirements; `validate_required_fields` returns **both** names when diameter and thickness are both missing; a round shape reports `width` as "Diameter" and a rectangular one as "Width". Confirm these fail before continuing
- [X] T004 Restructure `TypeShapeCompatibility` in `app/taxonomy.py` so requirements vary by shape. Today `required_dimensions` is keyed on type alone and `get_required_dimensions()` (`:93-101`) takes `shape` only as a compatibility gate — that is the structural reason the rule got restated in JavaScript
- [X] T005 Seed the table in `app/taxonomy.py` from [data-model.md](./data-model.md) §2, all 17 rows. Reproduce today's **effective** behaviour — the JS table, because it is the only one that runs — with exactly two rows changed. The Threaded Rod, Bar+Round and Channel rows each have a justification in §2; getting any of them wrong turns passing tests red at a distance
- [X] T006 Add `validate_required_fields(item_type, shape, values)` to `app/taxonomy.py` per [contracts/dimension-rules.md](./contracts/dimension-rules.md) §C1. It returns a message for **every** missing field, never just the first (FR-018), and names `width` as "Diameter" for round shapes
- [X] T007 Re-derive `get_required_dimensions()`, `get_compatible_shapes()` and `is_shape_compatible_with_type()` in `app/taxonomy.py` from the one table, so no method can answer from a stale second copy
- [X] T008 Run `nox -s tests`. T003 goes green

**Checkpoint**: one table, tested. User stories can begin.

---

## Phase 3: User Story 1 — Record a round plate by what it actually is (Priority: P1) 🎯 MVP

**Goal**: a round plate is recorded from diameter and thickness alone, on the Add form and
through the item API, with no invented length.

**Independent Test**: open Add Item, select Plate and Round, supply only diameter and
thickness, submit, and confirm the item exists with exactly those dimensions and no length.

### Tests for User Story 1

- [X] T009 [P] [US1] Add round-shape validation cases to `tests/unit/test_database.py`: `validate()` accepts a Plate+Round with width and thickness and no length, and rejects one missing either. There is no test for round-shape validation at all today — `test_validate_rectangular_item_requirements` (`:174`) is the nearest and uses Plate+Rectangular
- [X] T010 [P] [US1] Add create-path cases to `tests/unit/test_routes.py`: `POST /api/inventory/items` refuses a round plate with no thickness (400, message naming it), accepts one with diameter and thickness and no length, and names **both** when both are missing. The 21 existing tests built on `_minimum_payload` (`:1347`) must stay green — they are the check that enforcement did not overreach

### Implementation for User Story 1

- [X] T011 [US1] Replace the dimension branch of `InventoryItem.validate()` (`app/database.py:210-236`) with a call to `validate_required_fields`. Leave the JA-ID, material, item-type and positive-value checks alone. This deletes the third copy of the rules
- [X] T012 [US1] Enforce on the create paths in `app/main/routes.py` — the Add form POST and the JSON create path — beside the existing `required_fields` check (`:261`), after dimension parsing so an unparseable dimension still reports as one. Refusal shape per [contracts/dimension-rules.md](./contracts/dimension-rules.md) §C2. **Not** in `InventoryService`: e2e fixtures seed through it (research D2)
- [X] T013 [US1] Pass the rules table to the Add Item view in `app/main/routes.py`
- [X] T014 [US1] Render the table as a JSON constant in `app/templates/inventory/add.html` per [contracts/dimension-rules.md](./contracts/dimension-rules.md) §C3
- [X] T015 [US1] Create `app/static/js/dimension-requirements.js` owning four behaviours and nothing else: requirement marks and `required` attributes, the Width→Diameter label for round shapes, Shape-option filtering, and no fetch. It must not know about threading sections, carry-forward, barcode scanning or photos
- [X] T016 [US1] Delete the `typeShapeRequirements` literal and the methods that moved — `updateDimensionRequirements()` (`:280-322`), `updateShapeOptions()` (`:324-354`), `updateWidthLabel()` (`:356-366`) — from `app/static/js/inventory-add.js`, and call the shared module instead. The literal is deleted, not corrected
- [X] T017 [US1] In `tests/e2e/pages/add_item_page.py`: add a `thickness=` parameter to `fill_dimensions()` (`:101-110`), and **delete `DIAMETER_INPUT = "#diameter"` (`:23`)** or repoint it at `#width`. It matches no element in any template and `_fill_if_on_this_form` (`:93-99`) returns silently on `count() == 0`, so every `diameter=` argument in the suite has always set nothing
- [X] T018 [US1] Write the add-side scenarios in `tests/e2e/test_round_plate.py` (new file). Wait conditions per [quickstart.md](./quickstart.md): `expect(...).to_have_attribute('required', '')` rather than `get_attribute()`, `expect(width_label).to_have_text('Diameter')`, and **check `submit_and_wait()`'s return value** — it returns `False` when constraint validation refuses, and a caller that ignores it carries on as though the item exists. Assert the row exists; leave dimension-text assertions to US3
- [X] T019 [US1] Run `nox -s tests`, and `nox -s e2e` in the background

**Checkpoint**: issue #85's actual request is delivered. A round plate is recordable from two measurements.

---

## Phase 4: User Story 2 — The same rule everywhere the item is recorded (Priority: P2)

**Goal**: the Edit form enforces what it marks, and the edit path applies the same rule as
create.

**Independent Test**: create a round plate with only diameter and thickness, open it in the
Edit form, save unchanged — nothing is demanded; then clear the thickness and save — refused,
naming it.

### Tests for User Story 2

- [X] T020 [P] [US2] Add edit-path cases to `tests/unit/test_routes.py`: an edit that clears a required dimension is refused and names it; an edit that changes nothing on a length-less round plate succeeds

### Implementation for User Story 2

- [X] T021 [US2] Enforce on the edit path in `app/main/routes.py`, beside its `required_fields` check (`:660`), using the same call and the same refusal shape as T012
- [X] T022 [US2] Pass the rules table to the Edit Item view in `app/main/routes.py`
- [X] T023 [US2] In `app/templates/inventory/edit.html`: render the rules JSON, and remove the hard-coded asterisks — `Length *` (`:167`), `Width *` (`:179`), and the `'Diameter *'`/`'Width *'` strings in the inline script (`:458-461`). The asterisk is now driven by the requirement mark, so it must not be baked into the label text
- [X] T024 [US2] Wire `dimension-requirements.js` into `app/templates/inventory/edit.html`, replacing `updateFieldVisibility()`'s label swapping (`:441-466`) while leaving its threading-section toggle alone. Resolve `#required-dimensions-info` / `#required-dimensions-text` (`:160-162`) — either drive them from the module or delete them; leaving them present, empty and unexplained is the one option to avoid
- [X] T025 [US2] Add the edit-side scenarios to `tests/e2e/test_round_plate.py`: save unchanged, clear a required dimension and be refused, and change Shape from Rectangular to Round with a length present and confirm the length is retained rather than discarded (spec Story 2, scenario 6)
- [X] T026 [US2] Run `nox -s tests`, and `nox -s e2e` in the background

**Checkpoint**: an item that one path accepts, every path accepts. FR-006, FR-007 and FR-017 hold.

---

## Phase 5: User Story 3 — A round plate reads as a disc (Priority: P3)

**Goal**: a round plate with no length shows its diameter and thickness everywhere, and the
diameter is identifiable as one.

**Independent Test**: record a round plate with only diameter and thickness, then view it in
the list, in search results and in history, and confirm each shows `⌀6" × 0.25"` rather than
`6" × 0.25"` or nothing.

### Tests for User Story 3

- [X] T027 [P] [US3] Add `display_name` cases to `tests/unit/test_database.py`: a length-less round plate includes its diameter and thickness. The existing `test_display_name_with_dimensions_round` (`:217`, a Bar) must keep passing

### Implementation for User Story 3

- [X] T028 [US3] Fix `display_name` in `app/database.py:248-265`. Every dimension currently sits under `if self.length:` (`:257`), so a length-less round plate renders as `Steel Plate Round` with no dimensions at all; the ROUND branch (`:259`) also has no thickness term, so even a round plate that *has* a length loses its thickness. This reaches five API payloads (`routes.py:39, 1435, 1478, 1858, 2079`) and every screen showing an item's name
- [X] T029 [P] [US3] Fix `formatFullDimensions` in `app/static/js/components/item-formatters.js`. The `width && thickness` branch (`:61`) never emits ⌀, so a round plate renders identically to a rectangular one; only the `width`-alone branch (`:68`) emits it. Already wrong today, and FR-014 forbids it
- [X] T030 [US3] Add a Plate+Round item **with no length** to `DIMENSION_ITEMS` (`:25-107`) in `tests/e2e/test_dimensions_display.py`, with its expected rendering in `EXPECTED_DIMENSIONS` (`:110`) and `EXPECTED_LENGTH` (`:121`). No Plate+Round item and no length-less item exists anywhere in the suite today, which is why the missing ⌀ has gone unnoticed. Establish the table region with `expect()` before any `count()` or `text_content()`
- [X] T031 [US3] Run `nox -s tests`, and `nox -s e2e` in the background

**Checkpoint**: all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 [P] Update the item API reference in `docs/user-manual.md:1404-1416`. The dimension fields are documented as unconditionally optional; after FR-017 they are conditionally required, and a request missing one now returns 400. Say which combination requires what, and note that `width` carries the diameter for round items
- [X] T033 Verify the cause is fixed and not only the symptom: `grep -rn "typeShapeRequirements" app/` must return nothing, and `grep -rn "required_dimensions" app/` must find only `app/taxonomy.py`
- [X] T034 Regenerate documentation screenshots — `nox -s screenshots_headless`, then `nox -s screenshots_verify` — and commit the changed PNGs alongside the code. This is obligatory, not optional: the change touches `app/templates/**` and `app/static/js/**`, and CI blocks merge on stale screenshots. `user-manual/add_item_form.png` and `user-manual/edit_item_form.png` both show requirement asterisks that move
- [X] T035 Full green: `nox -s tests`, and `nox -s e2e` in the background. Then confirm `git status` is clean after the e2e run — if it is dirty, a screenshot test leaked into the session, which the constitution forbids
- [X] T036 Walk the manual scenarios in [quickstart.md](./quickstart.md) against `python app.py`, including the `curl` that must now return 400
- [X] T037 [P] Carry the plan's **Known gaps** into the pull request description — the latent shorten hole at `app/mariadb_inventory_service.py:500`, the dead `dimensions.diameter` reads, Channel's empty rule and its narrowed Shape dropdown. They are deliberate omissions, and a reviewer should see them as decisions rather than discover them as oversights

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all three user stories**. Everything downstream reads the table it builds
- **US1 (Phase 3)**: depends on Phase 2
- **US2 (Phase 4)**: depends on Phase 2, and in practice on T015 — the shared JS module is created in US1 and reused here. This is the one real cross-story dependency; it is a reuse, not a coupling, and US2 remains independently testable once it exists
- **US3 (Phase 5)**: depends on Phase 2 only. It touches display paths that no other story touches, so it could be done first if you wanted to see a round plate render correctly before you could create one
- **Polish (Phase 6)**: depends on every story you intend to ship

### Within each story

- Tests are written first and confirmed failing
- The rules table before anything that reads it
- Server enforcement before the front end that mirrors it, so the front end is a convenience rather than the only gate
- Unit tests before e2e — they run in under a second and catch most of it

### Parallel opportunities

Honest accounting for a single-developer project: the parallelism here is *within* a phase, not
across people.

- T009 and T010 — different test files
- T020 stands alone
- T027 and T029 — one Python file, one JavaScript file
- T032 and T037 — documentation, independent of each other
- **Not parallel**: T004–T007 all edit `app/taxonomy.py`; T012 and T013 both edit `app/main/routes.py`; T021 and T022 likewise; T023 and T024 both edit `edit.html`

---

## Implementation Strategy

### MVP

Phase 1 → Phase 2 → Phase 3, then stop and validate. That is issue #85's actual request: a
round plate recordable from a diameter and a thickness. It is shippable on its own — the Edit
form still enforces nothing (as it does today) and the display still hides dimensions on a
length-less item (as it does today), but nothing is *worse* than before and the invented
lengths stop.

### Incremental delivery

1. Setup + Foundational → one rules table, tested
2. + US1 → **MVP**: round plates recordable truthfully; validate independently
3. + US2 → the rule holds on every path; validate independently
4. + US3 → round plates read as discs; validate independently
5. Polish → screenshots, docs, full green

Ship US1 and US3 together if you would rather not see a round plate display without its
dimensions in the meantime — they are independent of each other and US3 is three tasks.

---

## Notes

- Commit per task or per logical group. Screenshots (T034) must land in the **same** change as
  the UI they document
- `[P]` means a different file and no incomplete dependency, nothing more
- The e2e rule is state, never duration: no `wait_for_timeout`, no `time.sleep`, no
  `networkidle`. The suite currently executes **zero** fixed waits and two features were spent
  getting there. `count()`, `text_content()`, `is_visible()`, `get_attribute()` and
  `is_checked()` do not poll — establish the region with `expect()` first, and be most careful
  with negative assertions, which pass trivially against a page that has not loaded
- No new pytest marker is needed; `--strict-markers` is on, so if you think you need one,
  register it in `pytest.ini` first
- No Alembic revision. If you find yourself writing one, something has gone wrong — `length` is
  already nullable and diameter is already the `width` column (research D8)
