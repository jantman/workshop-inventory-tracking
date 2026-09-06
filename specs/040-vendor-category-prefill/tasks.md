---

description: "Task list for feature 040 — a vendor's category is not the shop's category"
---

# Tasks: A Vendor's Category Is Not the Shop's Category

**Input**: Design documents from `/specs/040-vendor-category-prefill/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are included and are **not optional here**. Constitution IV requires that a
change altering behavior lands with tests covering that behavior, and three existing tests assert
the behavior being removed.

**Organization**: Grouped by user story. Each story is one of the doors the vendor's category
reaches a product through, and each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `[US1]`, `[US2]`, `[US3]`
- Every task names its file path.

## Path Conventions

Server-rendered Flask app at the repository root: `app/`, `tests/unit/`, `tests/e2e/`, `docs/`.
Run tests via `nox`, never `pytest` directly. Prefix nox with
`PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` and invoke `venv/bin/nox`.

---

## Phase 1: Setup

- [X] T001 Establish the baseline: run `venv/bin/nox -s tests` and record that it is green before any edit, so a later failure is attributable to this change and not inherited.

---

## Phase 2: Foundational

**No foundational work.** There is no schema change, no migration, no new module and no shared
helper to build first. Each user story edits files no other story edits, except the two shared
polish files handled in the final phase. This phase exists to say so explicitly rather than to be
skipped silently.

---

## Phase 3: User Story 1 — Capturing a DigiKey order leaves the category to the operator (P1) 🎯 MVP

**Goal**: A product created by capturing a vendor order arrives uncategorized. The category tree
gains nothing from a capture.

**Independent test**: Capture a DigiKey order whose part detail states a category; the created
products have an empty category and the tree is unchanged.

### Tests for User Story 1

- [X] T002 [US1] Rewrite `TestEnrichment::test_enrichment_fills_the_product_the_order_could_not` in `tests/unit/test_digikey_capture.py` so it asserts the manufacturer and the specification rows are filled **and** `product.category_path` is falsy, replacing the `assert product.category_path is not None` that currently encodes the defect. Keep the test's name accurate to what it now proves.
- [X] T003 [P] [US1] Add a test to `tests/unit/test_digikey_capture.py` asserting that capturing an order whose part detail states a category creates products carrying no category — named for the rule (a vendor's category is not the shop's), with a docstring citing spec FR-001 and the tree-is-emergent reason.
- [X] T004 [P] [US1] Add a test to `tests/unit/test_digikey_capture.py` asserting a capture whose part lookup fails still creates the product with an empty category and reports no error (spec FR-006, US1 scenario 3), so "blank is ordinary" is held by an assertion and not only by a sentence.

### Implementation for User Story 1

- [X] T005 [US1] In `app/catalog_service.py`, remove the `category_path=self._validate_category_path(part.category_path if part else None)` argument from the `Product(...)` construction in `_create_digikey_product`, and replace the comment above it with one stating the new rule and why it changed — the field is free-form and the tree is built from the values in use, so a vendor value left unchanged once becomes a branch of the shop's taxonomy (issue #138, spec FR-001).

**Checkpoint**: `venv/bin/nox -s tests` green. The reported defect is closed; US2 and US3 close the
other doors.

---

## Phase 4: User Story 2 — The single-part capture page, and the form a scan opens (P2)

**Goal**: Neither DigiKey capture surface pre-loads the category into a field that will be
recorded, and the single-part page can still file a product because it now offers an empty
Category field of its own.

**Independent test**: Look up a part whose detail states a category and create the product without
touching Category — it is uncategorized; type a category and it is stored. The Add Product form
opened by a scan of an unknown part has an empty Category box.

### Tests for User Story 2

- [X] T006 [P] [US2] Add a unit test in `tests/unit/test_vendor_category.py` (a new file — `test_product_routes.py` is scoped to reaching a product by its printed code, and these are the feature's own tests) that GETs the single-part capture page for a looked-up part and asserts the rendered HTML contains exactly one input named `category_path`, that it is not `type="hidden"`, and that its value is empty — the invariants in `contracts/digikey-part-capture-form.md`.
- [X] T007 [P] [US2] Add a unit test in `tests/unit/test_vendor_category.py` that the same page still displays DigiKey's own category in its read-only "What DigiKey says" list (spec FR-005) — reading and displaying the vendor's value is retained, only recording it is removed.
- [X] T008 [P] [US2] Add a unit test in `tests/unit/test_vendor_category.py` that the Add Product form opened with the scan-prefill query parameters for an unknown DigiKey part renders an empty Category input while its description, manufacturer and part-number prefills are unchanged (spec FR-010).
- [X] T009 [US2] Add two E2E tests to `tests/e2e/test_digikey_part.py`: look up `1866-3027-ND`, assert `#category_path` is present and `to_have_value("")`, create the product without typing, and assert the product page shows no category; then repeat typing `electronics/power/power supplies` and assert `#product-category` has that text. Wait on `expect()` conditions only — landing on the product page is the signal the write finished, as the neighbouring tests already do. No fixed wait.

### Implementation for User Story 2

- [X] T010 [US2] In `app/templates/product/digikey_part_review.html`, delete the hidden `category_path` input from the create form and add a visible Category field in its place, above or beside the Storage Location / Sub-Location row, using the exact markup contract in `contracts/digikey-part-capture-form.md` — `id="category_path"`, `name="category_path"`, `maxlength="512"`, `list="category-suggestions"`, an always-empty value, a sibling `<datalist id="category-suggestions">`, and the same helper text the shared partial uses. Add a comment recording that the ids are what `catalog-suggestions.js` binds and that the value is never seeded from the part.
- [X] T011 [P] [US2] In `app/product/routes.py`, remove the `'category_path': part.category_path,` entry from the `prefill.update({...})` in `product_new`'s scan branch, leaving every other pre-loaded value in place, with a brief comment naming spec FR-010 and the reason (a pre-loaded value that is simply accepted is still the vendor's value becoming a branch).

**Checkpoint**: `venv/bin/nox -s tests` green; the new E2E test passes.

---

## Phase 5: User Story 3 — Enriching an existing product does not file it (P3)

**Goal**: Enrichment fills the manufacturer and the specifications and never the category, whether
or not the category is blank.

**Independent test**: Enrich a product with a blank category from a part detail stating one — the
category is still blank, the manufacturer and specifications were still written.

### Tests for User Story 3

- [X] T012 [US3] In `tests/unit/test_order_enrichment.py`, replace `TestAMatchedProductIsEnriched::test_a_blank_category_is_filled` with a test asserting a blank category is **left** blank by enrichment, renamed to say so, with a docstring recording that this assertion was inverted deliberately by feature 040 and why — so a future reader does not "restore" it as a regression.
- [X] T013 [US3] Update the module docstring of `tests/unit/test_order_enrichment.py`, which currently lists "no category" among the gaps DigiKey fills, to name the two gaps enrichment still fills and to state that the category is deliberately not one of them.
- [X] T014 [P] [US3] Add a test to `tests/unit/test_order_enrichment.py` asserting a product the operator has already filed keeps its own category across a capture that enriches it (spec US3 scenario 2) — the fill-gaps-only rule's other half, which must keep holding.

### Implementation for User Story 3

- [X] T015 [US3] In `app/catalog_service.py`, remove the `if part.category_path and not product.category_path: product.category_path = ...` clause from `_enrich_digikey_product`, leaving the manufacturer and specification clauses untouched, and update the method's docstring so it describes what enrichment fills now and names the category as a deliberate exclusion rather than an oversight.

**Checkpoint**: all three doors shut; `venv/bin/nox -s tests` green.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 [P] In `app/templates/product/order_review.html`, correct the unenriched-lines warning, which tells the operator that thin lines "arrive without a manufacturer, category or specifications" and so implies that enriched lines arrive with a category. State what is now true: they arrive without a manufacturer or specifications (spec FR-007).
- [X] T017 [P] In `docs/user-manual.md`, correct the three passages that promise DigiKey's category — the order-capture section ("the manufacturer, the category and the full parametric detail"), the single-part section ("the datasheet, the photograph, DigiKey's category and…") and the backfill section ("manufacturer, category, datasheet, photograph…") — so the manual describes what the capture records. Where it is useful, say plainly that a captured product arrives uncategorized and is filed by the operator, because a vendor's catalog is not this workshop's shelves.
- [X] T018 Verify no other reader treats a vendor category as a value to record: re-run the search behind `research.md`'s table (`grep -rn "category_path" app/`) and confirm the only remaining vendor-side use is display and payload parsing. If a fifth site is found, add it as a task rather than fixing it silently.
- [X] T019 Run `venv/bin/nox -s lint` and `venv/bin/nox -s tests` and confirm both are green. **Note**: `nox -s tests` is green (2486 passed). `nox -s lint` fails repo-wide on pre-existing `E501`s in files this feature does not touch, and is not run by CI (`.github/workflows/test.yml` runs `tests`, `coverage` and `e2e`); the lines this feature added are clean. Cleaning the repo's existing lint debt is not this bug fix's job.
- [X] T020 Run `venv/bin/nox -s e2e` **detached** (`nohup` / background) with polling — it takes about 14 minutes warm and outlasts a 10-minute tool timeout — and confirm it is green and that the working tree is left clean. **Result**: 793 passed in 16m55s, zero failures, working tree left clean.
- [X] T021 Walk the by-hand checks in [quickstart.md](./quickstart.md) for at least the order capture and the single-part page: the category tree gains no branch, and the new Category field is empty, editable and suggestion-backed. **How it was actually verified**: the single-part page's checks were driven through a real browser against a real server by the two new E2E tests, which is the by-hand walk automated. The order-capture check was made against the tree itself rather than by eye — `TestTheCategoryTree` in `tests/unit/test_vendor_category.py` asserts the set of tree paths is identical before and after a capture (SC-001), with a companion asserting an operator's own branch still appears so the first is not passing on a suppressed tree. A by-hand capture of a live DigiKey order was not performed: it needs DigiKey credentials this environment does not hold, and the recorded fixture the tests use is that same order's response.

---

## Dependencies

- **T001** precedes everything (baseline).
- **Phase 2** is empty; user stories may begin immediately after T001.
- **US1 (T002–T005)**, **US2 (T006–T011)** and **US3 (T012–T015)** are independent of one another.
  They touch disjoint files, except that T005 and T015 both edit `app/catalog_service.py` — in
  different methods, but sequence them rather than running them in parallel.
- Within each story, tests are written before the implementation task they cover.
- **Phase 6** follows all three stories: T016 and T017 describe the finished behavior, and T019–T021
  gate on all of it.

## Parallel Opportunities

- T003 and T004 are parallel with each other (same file, distinct new tests — coordinate the write).
- T006, T007 and T008 are parallel (distinct new tests in one file).
- T011 is parallel with T010 (different files).
- T014 is parallel with T012/T013's edits only if the file writes are coordinated; otherwise
  sequence them.
- T016 and T017 are parallel (different files).

## Implementation Strategy

**MVP is User Story 1 alone**: it closes the reported defect on the path where it was found, and it
is one deleted argument plus its tests. Ship order US1 → US2 → US3 → polish, and every stopping
point in between is a coherent, tested state.

Do not stop at the MVP in this change, though: US2 and US3 write the same wrong value into the same
field through quieter doors, and leaving them is exactly the "cost paid in the tree, not in the one
record" the issue describes.
