---
description: "Task list for the initial category taxonomy"
---

# Tasks: Initial Category Taxonomy for the Existing Workshop

**Input**: Design documents from `specs/025-category-taxonomy/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/http-endpoints.md](./contracts/http-endpoints.md),
[quickstart.md](./quickstart.md)

**Tests**: included, and **not optional here**. Constitution IV requires that changes altering
behavior land with tests covering that behavior, and that `nox -s tests` and `nox -s e2e` pass
before merge. These are governance tasks, not a TDD preference.

**Organization**: grouped by user story. User Story 1 is already delivered — its tasks are
recorded as complete rather than omitted, so the trail from spec to record stays legible.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable — different file, no dependency on an incomplete task
- **[Story]**: US1, US2, US3 from [spec.md](./spec.md)

## Path Conventions

Single project at the repository root: `app/` for runtime code, `tests/unit/` and `tests/e2e/`
for tests, `docs/` for operator-facing material. Commands run against `venv/` per Constitution
"Local commands".

---

## Phase 1: Setup

**Purpose**: establish a clean baseline before touching anything.

- [ ] T001 Confirm the working tree is clean on branch `issues/98` and record a green baseline by running `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` from the repository root

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the reference data every user story reads. Nothing in Phase 4 can start without it.

**⚠️ CRITICAL**: T002 and T003 block all of User Story 2.

- [ ] T002 Create `app/utils/catalog_taxonomy.py` exporting `CATEGORY_PATHS: tuple[str, ...]` — all 142 branches from `docs/category-taxonomy.md` including roots and intermediate parents, each already in canonical form (lowercase, `/`-joined), sorted, no duplicates. Standard library only: no Flask, no database, no file I/O, matching `app/utils/category.py` in kind. Module docstring states that `docs/category-taxonomy.md` is the authority and that `tests/unit/test_catalog_taxonomy.py` enforces the agreement
- [ ] T003 Add `SPECIFICATION_KEYS: tuple[str, ...]` to `app/utils/catalog_taxonomy.py` — the distinct keys from the record's specification-key registry, trimmed, sorted, no case-folded duplicates, none over 100 characters
- [ ] T004 Create `tests/unit/test_catalog_taxonomy.py` asserting the `CATEGORY_PATHS` invariants from [data-model.md](./data-model.md): every element equals `category.canonical(element)`, at most 3 segments (FR-004), at most 512 characters, every non-root element's parent also present, no duplicates, sorted, and no parent with more than 20 direct children (SC-003)
- [ ] T005 Add to `tests/unit/test_catalog_taxonomy.py` a test that parses the branch tables of `docs/category-taxonomy.md` and asserts the paths it names equal `CATEGORY_PATHS` exactly, and that the registry's keys equal `SPECIFICATION_KEYS` — this is what makes FR-019's record-versus-reference-data obligation a red gate instead of a hope

**Checkpoint**: the taxonomy is importable and provably matches the record.

---

## Phase 3: User Story 1 — Settle the tree and write it down (Priority: P1) ✅ DELIVERED

**Goal**: the workshop owner and an assistant converge on a tree in a working session, and the
result is written down with a one-line statement per branch, the naming conventions, and the
tag boundary.

**Independent Test**: hand the record to a reader who was not in the session with twenty
in-scope bin labels and compare their placements against the owner's.

**Status**: completed in session on 2026-08-23 and committed (`8b22963`, `34e567e`, `158d960`).
Recorded here because Phase 2 derives from it and because FR-001 forbids anything downstream
inventing it.

- [X] T006 [US1] Run the interactive session with the workshop owner and record the outcome in `docs/category-taxonomy.md` — seam rule, five tie-break rules, naming conventions, tags, and every branch with a one-line definition (FR-001..FR-007, FR-020..FR-022)
- [X] T007 [US1] Walk every labelled bin in areas 2, 3, 5 and 6 of `specs/025-category-taxonomy/shop-inventory.txt` against the tree and record the mapping, the gaps and the ambiguities in `specs/025-category-taxonomy/coverage-pass.md` (FR-008, SC-004, SC-005)
- [X] T008 [US1] Add the specification-key registry and the vendor-name normalizations to `docs/category-taxonomy.md` (FR-023, FR-024, FR-025)

---

## Phase 4: User Story 2 — File into a branch nothing occupies yet (Priority: P2) 🎯 MVP of the remaining work

**Goal**: every branch of the record is offered on the filing screen before any product sits in
it, and choosing one stores the record's path exactly.

**Independent Test**: with no product in `fasteners/machine screws & bolts/socket head cap`,
open the add-product form, select that branch from the suggestions without typing it out, save,
and confirm the stored path is that string character for character.

- [ ] T009 [US2] Union `CATEGORY_PATHS` into `CatalogService.list_categories` in `app/catalog_service.py` — deduplicate on the canonical path, apply the existing `prefix` filter to the union rather than to the in-use half only, keep the sorted `list[str]` return shape (FR-012, FR-013, FR-017, FR-018)
- [ ] T010 [US2] Union `CATEGORY_PATHS` into `CatalogService.category_tree` in `app/catalog_service.py` — an unoccupied branch yields `count: 0`, every entry gains `in_taxonomy: bool`, and an in-use path the taxonomy does not name is never dropped (FR-017, FR-018, and the state table in [data-model.md](./data-model.md))
- [ ] T011 [US2] Add tests to `tests/unit/test_catalog_service.py` covering both unions: all 142 branches returned from an empty catalog (FR-012, SC-009); an in-use path absent from the taxonomy still returned (FR-015, FR-017); a path both offered and in use appearing exactly once (FR-018); `prefix` filtering the union; and each of the three reachable `in_taxonomy`/`count` states from [data-model.md](./data-model.md)
- [ ] T012 [P] [US2] Add a regression test to `tests/unit/test_category_rename.py` asserting `rename_category` still raises `ValidationError` for a taxonomy branch that no product occupies — the browse page now surfaces those rows, and this behavior is what the template gating in T014 depends on (research D4)
- [ ] T013 [US2] Rewrite the explanatory paragraph in `app/templates/product/categories.html`, which currently asserts "A category exists because a product is in it … There is nothing here to set up" — now false. Say what is true: the branches come from `docs/category-taxonomy.md`, a branch with no products is on offer rather than in use, and a branch the record does not name is one somebody typed
- [ ] T014 [US2] In `app/templates/product/categories.html`, render the Rename button only when the row's `count` is greater than zero, and mark rows where `in_taxonomy` is false. An unoccupied branch is renamed by editing the record and `app/utils/catalog_taxonomy.py`, because there is nothing in the database to rewrite (research D4, FR-019)
- [ ] T015 [US2] Create `tests/e2e/test_category_taxonomy.py` covering the four scenarios in [quickstart.md](./quickstart.md): filing into an unoccupied branch; a branch both offered and occupied appearing once on the browse page; the Rename control present on an occupied branch and absent on an unoccupied one; and a path outside the tree still saving. Seed with `live_server.add_test_data`, wait on observable state only — no `wait_for_timeout`, no `networkidle` — and establish the list region with `expect(...)` before any `count()`, since the "appears once" assertion is the kind that passes for the wrong reason against a region that has not settled (Constitution IV)
- [ ] T016 [US2] Regenerate documentation screenshots for the changed template with `venv/bin/nox -s screenshots_headless`, verify with `venv/bin/nox -s screenshots_verify`, and commit **only** the images this change actually altered — the session churns images unrelated to the change, and committing the churn destroys review signal

**Checkpoint**: SC-008 and SC-009 hold — every branch of the record is selectable while filing,
with nothing else open.

---

## Phase 5: User Story 3 — File the products already in the catalog (Priority: P3)

**Goal**: the products captured during the issue #80 verification get categories, which is the
first exercise of the tree against things rather than bin labels.

**Independent Test**: every product in the catalog either carries a path the record names, or is
deliberately uncategorized because it falls in a deferred area.

- [ ] T017 [US3] File each existing product into a branch through the product edit screen, leaving anything from the deferred areas (machining, general DIY, 3D printing, hand tools, automotive) uncategorized rather than forcing it into a branch (FR-014, FR-021)
- [ ] T018 [US3] Verify SC-006 by checking that no category path in the catalog is absent from `docs/category-taxonomy.md`, except paths that predate the tree; where filing revealed a branch that does not work, rename it and update `docs/category-taxonomy.md` and `app/utils/catalog_taxonomy.py` in the same change (FR-019)

**Checkpoint**: the tree has survived contact with real products.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T019 Union `SPECIFICATION_KEYS` into `CatalogService.list_specification_names` in `app/catalog_service.py`, feeding the existing `specification-name-suggestions` datalist. **This is the declared judgment call from [plan.md](./plan.md) and is cleanly droppable**: no functional requirement demands it, but SC-010 has no other mechanism and specification names are the one vocabulary in the application with no rename to repair drift (research D6)
- [ ] T020 Add a test to `tests/unit/test_catalog_service.py` asserting `list_specification_names` returns the record's keys from an empty catalog and still returns an in-use name the record does not list (SC-010). Skip if T019 is dropped
- [ ] T021 [P] Link `docs/category-taxonomy.md` from `docs/user-manual.md` where categories are described, so the record is reachable from the operator documentation rather than only from this feature directory
- [ ] T022 Run the full gates: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`, then `nox -s e2e` **detached** (`nohup … &` and poll) because it runs about 14 minutes warm and outlasts a 10-minute tool timeout — budget 20 minutes cold
- [ ] T023 Confirm the E2E run left the working tree clean, per Constitution IV. A dirty tree after `nox -s e2e` means screenshot tests leaked into the session, which is a bug in the run and not in this feature
- [ ] T024 Update `specs/025-category-taxonomy/checklists/requirements.md` notes to record that the software half shipped, and open the pull request for `issues/98` against `main`

---

## Dependencies

```text
Phase 1 (T001)
   └─> Phase 2 (T002 → T003 → T004 → T005)        [foundational; blocks Phase 4]
          └─> Phase 4 / US2 (T009 → T010 → T011, T012, T013 → T014, T015, T016)
                 └─> Phase 5 / US3 (T017 → T018)
                        └─> Phase 6 (T019 → T020, T021, T022 → T023 → T024)

Phase 3 / US1 (T006–T008) — already delivered; Phase 2 derives from it
```

**Story independence**: US1 stands alone and already delivers value — with the record and no
software change, products can be filed consistently by hand. US2 depends on Phase 2 but not on
US3. US3 depends on US2 only for convenience; the products could be filed by typing paths from
the record.

**Within-file ordering**: T009 and T010 touch the same file and are sequential. T013 and T014
touch the same template and are sequential. T004 and T005 are the same test file and are
sequential.

## Parallel opportunities

- **T012** runs alongside T009–T011 — different file (`tests/unit/test_category_rename.py`), no
  dependency on the unions.
- **T021** runs alongside anything in Phase 6 — documentation only.
- Genuine parallelism is limited here, and that is the honest picture: the feature is three
  edits to one service file and two edits to one template. Splitting it further would invent
  coordination cost for no gain.

## Implementation strategy

**MVP of the remaining work is Phase 2 + Phase 4.** That is the whole of FR-012 and FR-016
through FR-019, and it is what turns the record from a document the operator has to keep open
in another window into the list the filing screen offers.

Phase 5 is operator work rather than code, and is the step most likely to send a branch back for
renaming — which is why it comes before the polish phase rather than after.

Phase 6's first task is the one to cut if the change is judged larger than the problem. Nothing
else depends on it.
