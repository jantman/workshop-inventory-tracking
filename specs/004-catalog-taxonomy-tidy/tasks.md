---

description: "Task list for feature 004 — Keep the Catalogue Tidy"
---

# Tasks: Keep the Catalogue Tidy

**Input**: Design documents from `specs/004-catalog-taxonomy-tidy/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Branch**: `issues/61`

**Tests**: Included, and **not optional here**. Constitution IV requires that "changes that alter behavior MUST land with tests covering that behavior", and every task below alters behavior. Coverage is *not* a target — write the test that would have caught the bug, and stop.

**Organization**: Grouped by user story so each ships and is validated on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1–US4)
- Every task names the exact file it touches

## Path Conventions

Existing repository layout, unchanged. Application code in `app/`, tests in `tests/unit/` and `tests/e2e/`, migrations in `migrations/versions/`. There is no `src/`.

---

## Phase 1: Setup

**Purpose**: Know that anything that breaks later, this feature broke.

- [ ] T001 Establish a green baseline on `issues/61` before changing anything: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and `nox -s e2e` (15-minute tool timeout). Record any pre-existing failure rather than silently inheriting it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The schema column every later slice reads or writes, plus the two shared pieces US1 and US2 both build on.

**⚠️ CRITICAL**: No user story work begins until T002–T004 are done. T005–T007 block only US1/US2.

- [ ] T002 Add `sub_location = Column(String(100), nullable=True)` to `Product` and a `sub_location` entry to `Product.to_dict()` in `app/database.py`, mirroring `inventory_items.sub_location` at line 60
- [ ] T003 Create the Alembic revision `migrations/versions/b1a0c0d10006_add_product_sub_location.py` adding `products.sub_location`, with a `downgrade()` that drops it — follow the existing `b1a0c0d1000N` catalogue series
- [ ] T004 Exercise the revision against **MariaDB**, not SQLite: `venv/bin/python manage.py db upgrade`, then `db downgrade -1`, then `db upgrade` again. Constitution V requires the downgrade to have been run.
- [ ] T005 [P] Add an `add_test_products(products_data)` helper to the live-server class in `tests/e2e/test_server.py`, built on `CatalogService`, alongside the existing `add_test_data` (line 134) and `add_material_taxonomy`. The rename e2e tests need several products across a category subtree, and driving the add form costs ~3s each.
- [ ] T006 [P] Create the shared confirmation modal partial `app/templates/product/_rename_modal.html`, parameterized for a "category" or "tag" subject — Bootstrap 5.3 modal, a form posting to a URL the including page supplies, a target-name input, and an impact/warning region the script fills
- [ ] T007 [P] Create `app/static/js/taxonomy-rename.js` — a plain IIFE matching `catalog-suggestions.js`. It populates the modal from the clicked row's data attributes, reports impact from data **already rendered on the page** (category: sum of the source path's count and its descendants'; tag: the source's count plus whether the target name matches an existing tag, i.e. a merge), warns on a collision the server will refuse, and submits. It performs no fetch — see decision D7 in `research.md`.

**Checkpoint**: schema in place and reversible; the shared rename UI exists. User stories can begin.

---

## Phase 3: User Story 1 — Rename a category (Priority: P1) 🎯 MVP

**Goal**: Renaming a category carries its sub-categories and every product beneath them in one action, and refuses rather than merges when the target is taken.

**Independent Test**: Seed products under `elctronics`, `elctronics/passives`, `elctronics/passives/resistors` and `elctronics-surplus`. Rename `elctronics` → `electronics`. The first three follow; the fourth is untouched. Then attempt each refusal and confirm nothing changed.

### Tests for User Story 1

- [ ] T008 [P] [US1] Unit tests for the rename path arithmetic in `tests/unit/test_category.py`: prefix rewrite at each depth, the separator boundary (`elctronics-surplus` must NOT be rewritten under a rename of `elctronics`), self-nesting detection, and canonicalization of both operands
- [ ] T009 [P] [US1] Unit tests for `rename_category` in `tests/unit/test_catalog_service.py`: subtree carried; sibling-by-prefix untouched; each of the six refusals in `data-model.md`'s validation table raises `ValidationError` naming the obstruction; and — the one that matters most — **after each refusal, every product's `category_path` is unchanged** (SC-005)

### Implementation for User Story 1

- [ ] T010 [US1] Add the pure functions `rename_descendant(path, old_ancestor, new_ancestor)` and `would_nest_within(new_path, old_path)` to `app/utils/category.py`, stdlib-only, alongside the existing `canonical` / `is_descendant` / `descendant_like_pattern`
- [ ] T011 [US1] Implement `CatalogService.rename_category(old_path, new_path)` in `app/catalog_service.py` per [`contracts/catalog-service.md`](./contracts/catalog-service.md) — one `self._session()` block, all six checks before any write, `ValidationError` on refusal so the context manager rolls back. Select the subtree with the existing `descendant_like_pattern(...)` + equality pair, as `list_categories()` already does.
- [ ] T012 [US1] Add `POST /products/categories/rename` to `app/product/routes.py` — read `old_path` / `new_path`, call the service, flash success (old name, new name, product count) or flash the `ValidationError` message, redirect to `GET /products/categories`. Thin: no ORM query in the route.
- [ ] T013 [US1] Update `app/templates/product/categories.html` — expose each row's path and count as data attributes, add a per-row rename button, include `_rename_modal.html` configured for categories, and include `taxonomy-rename.js`
- [ ] T014 [US1] E2E `tests/e2e/test_category_rename.py` — seed via `add_test_products`, cover the carry, the prefix sibling, and at least the collision and self-nesting refusals. The submit navigates, so `expect()` on the resulting page is the whole wait; assert the refusal cases against the rendered tree, not against a `count()` on an unestablished region.

**Checkpoint**: US1 is independently usable. A misspelled category is now a one-action fix.

---

## Phase 4: User Story 2 — Rename or merge a tag (Priority: P1)

**Goal**: A tag can be renamed, and renaming onto an existing tag merges the two with no product carrying the survivor twice.

**Independent Test**: Tag one product `surpluss`, another `surplus`, a third with both. Rename `surpluss` → `surplus`. One tag remains, carrying all three, each once.

### Tests for User Story 2

- [ ] T015 [US2] Unit tests for `rename_tag` and `tag_list_with_counts` in `tests/unit/test_catalog_service.py`: plain rename; merge; **a product carrying both tags survives the merge carrying the survivor exactly once**; merging `a`→`b` and `b`→`a` on equivalent data leaves the same product set; each refusal raises; counts include a zero-count orphan tag. *(Same file as T009 — sequence them, do not run both in parallel.)*

### Implementation for User Story 2

- [ ] T016 [US2] Implement `CatalogService.rename_tag(old_name, new_name)` in `app/catalog_service.py` — normalize as `_attach_tag()` already does, then either write `tag.name` or move each product that does not already carry the survivor and delete the source tag. The membership check is what turns "already carries both" from an `IntegrityError` into the no-op FR-010 requires.
- [ ] T017 [US2] Implement `CatalogService.tag_list_with_counts()` in `app/catalog_service.py` returning `[{'id', 'name', 'count'}]` alphabetically, including zero-count tags — mirrors `category_tree()`
- [ ] T018 [US2] Add `GET /products/tags` and `POST /products/tags/rename` to `app/product/routes.py`, matching the categories handlers. The success flash must distinguish a merge from a rename.
- [ ] T019 [US2] Create `app/templates/product/tags.html` — a `list-group` structured like `categories.html`: tag name, count badge, link to `/products?tag=...`, rename button, row data attributes, `_rename_modal.html` configured for tags, and `taxonomy-rename.js`
- [ ] T020 [US2] Add cross-links between `app/templates/product/categories.html` and `app/templates/product/tags.html` in each page's `page_actions` block, so both are reachable from the catalogue
- [ ] T021 [US2] E2E `tests/e2e/test_tag_rename.py` — seed via `add_test_products`, cover the plain rename, the merge, and the product that carried both

**Checkpoint**: both P1 stories done. The catalogue's typed vocabulary is repairable.

---

## Phase 5: User Story 3 — One vocabulary for locations and vendors (Priority: P2)

**Goal**: Location and vendor suggestions draw on both halves of the application, in both directions, with no publishing step.

**Independent Test**: Record a vendor on metal stock, see it offered on a product purchase; record a location on a product, see it offered on the Add Item form.

### Implementation for User Story 3

- [ ] T022 [US3] Create `app/services/vocabulary.py` with `VocabularyService` per [`contracts/vocabulary-service.md`](./contracts/vocabulary-service.md). **Move** `FIELD_SUGGESTION_COLUMNS` and `get_field_value_suggestions` from `app/mariadb_inventory_service.py:776-908` — preserve the ranking, LIKE-escaping, clamping, over-fetch and case-insensitive dedup exactly, including the comment explaining why backend failures are not swallowed. Widen `location`, `sub_location` and `vendor` to their catalogue columns; merge and re-rank across sources in Python (decision D9), not with a SQL UNION.
- [ ] T023 [US3] Delete `FIELD_SUGGESTION_COLUMNS` and `get_field_value_suggestions` from `app/mariadb_inventory_service.py` — no delegating shim
- [ ] T024 [US3] Point `GET /api/inventory/field-suggestions/<field>` in `app/main/routes.py` at `VocabularyService`. Path, query parameters, JSON shape and the `ValueError`→400 / `Exception`→500 handling all stay exactly as they are — that is what lets the metal stock forms and `field-autocomplete.js` go untouched.
- [ ] T025 [US3] **Move** the existing suggestion unit tests from `tests/unit/test_mariadb_inventory_service.py` into a new `tests/unit/test_vocabulary.py` — moved, not rewritten, so the ranking/escaping/dedup coverage survives intact
- [ ] T026 [US3] Add the union cases to `tests/unit/test_vocabulary.py`: catalogue-only value offered; metal-stock-only value offered; a value in both differing only in case offered **once**; `sub_location` scoped by `location=` filters each source against its own location column; `thread_size` and `purchase_location` still read metal stock only; a value on an inactive metal stock row is still offered (FR-019)
- [ ] T027 [P] [US3] In `app/templates/product/_form_fields.html`, wrap `#location` in a `position-relative` div and add `<div id="location-suggestions" class="dropdown-menu position-absolute w-100">`, matching `app/templates/inventory/add.html:253-261`
- [ ] T028 [P] [US3] Include `field-autocomplete.js` in `app/templates/product/add.html` and `app/templates/product/edit.html`, alongside the `catalog-suggestions.js` they already load
- [ ] T029 [P] [US3] Add the same dropdown markup around `#vendor` in `app/templates/product/purchase_add.html` and include `field-autocomplete.js`
- [ ] T030 [P] [US3] Add the same dropdown markup around `#vendor` in `app/templates/product/capture.html` and include `field-autocomplete.js`. Leave `#identifier_vendor` in `add.html` alone — that is an identifier's vendor, not a purchase vendor, and is out of scope.
- [ ] T031 [US3] Extend `tests/e2e/test_field_autocomplete.py` with the cross-half cases: a metal stock vendor offered on a purchase form, a product location offered on the Add Item form, and a non-matching value still accepted. Wait with `expect(dropdown.locator('.dropdown-item')).to_have_count(n)` — `render()` appends only after its `fetch` resolves, so the rendered item is a complete signal (CLAUDE.md pattern C). Assert the negative case as `expect(dropdown).not_to_be_visible()` **after** a positive assertion has established the component is live.

**No JavaScript is written for this story.** `field-autocomplete.js:218-240` already binds `#location`, `#sub_location` (scoped by `#location`) and `#vendor` on DOM ready and skips any target whose dropdown is absent; the catalogue's inputs already carry those ids.

**Checkpoint**: the two halves share one vocabulary. Drift stops here.

---

## Phase 6: User Story 4 — Record a product's sub-location (Priority: P3)

**Goal**: A product records a location and a sub-location, both suggested, matching metal stock.

**Independent Test**: Save a product with location `Drawer 3` and sub-location `Bin 7`; both persist and display. On a second product, typing `Drawer 3` then focusing sub-location offers `Bin 7`.

### Tests for User Story 4

- [ ] T032 [US4] Unit tests in `tests/unit/test_catalog_service.py`: `sub_location` round-trips through `create_product` and `update_product`; a product created without one has `None` and that is not an error (FR-023); `update_product` accepts the field rather than raising "Not editable". *(Same file as T009/T015 — sequence.)*

### Implementation for User Story 4

- [ ] T033 [US4] Add `sub_location` to `CatalogService.create_product()` (after `location`) and to the `editable` set plus its assignment branch in `update_product()` at `app/catalog_service.py:462-466`. Omitting the `editable` entry makes editing a product **start failing** once the form submits the field — a field absent from that set raises rather than being ignored.
- [ ] T034 [US4] Add `sub_location` to `_form_product_fields()` in `app/product/routes.py:43` — the single definition of what the add and edit forms submit
- [ ] T035 [US4] Add the Sub-Location input to `app/templates/product/_form_fields.html` beside Storage Location, with the `position-relative` wrapper and `<div id="sub_location-suggestions" ...>`; the component scopes it by `#location` automatically
- [ ] T036 [US4] Display `sub_location` alongside `location` in `app/templates/product/detail.html`, and in `app/templates/product/search.html`'s location column if it reads naturally there
- [ ] T037 [US4] Extend `tests/e2e/test_product_crud.py` with the sub-location round-trip and the scoped-suggestion case

**Checkpoint**: all four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T038 [P] Update `docs/user-manual.md` — the Product Catalogue section (line 475 onward) documents the categories page at line 704 as browse-only; document renaming a category, the new tags page, renaming/merging a tag, product sub-location, and that location and vendor now suggest across both halves
- [ ] T039 Regenerate documentation screenshots: `nox -s screenshots_headless` then `nox -s screenshots_verify`. Constitution workflow requires this whenever `app/templates/**` or `app/static/js/**` change. `tests/e2e/screenshot_config.yaml` currently captures no product-catalogue page, so expect **no** image diff — but run it and commit anything that does change, and confirm the working tree is clean afterward.
- [ ] T040 [P] Run `nox -s lint` (advisory) over the files this feature added or changed. Do not mass-reformat existing files — that destroys review signal.
- [ ] T041 Full suites green: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and `nox -s e2e` with a **15-minute tool timeout**. An `e2e` run must leave the working tree clean.
- [ ] T042 Walk `quickstart.md`'s manual validation for all four stories against a running app, including every refusal case in the US1 table

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: none
- **Phase 2 (Foundational)**: T002 → T003 → T004 must be sequential (model, then revision, then exercise it). T005/T006/T007 are independent of that chain and of each other.
- **Phases 3–6 (Stories)**: all require T002–T004. US1 and US2 additionally require T006 and T007; US1 and US2's e2e tasks require T005.
- **Phase 7 (Polish)**: after whichever stories are being shipped

### Story dependencies

- **US1 (P1)** — after Foundational. No dependency on another story.
- **US2 (P1)** — after Foundational. Reuses T006/T007, which is why they are foundational rather than inside US1; US2 does not depend on US1 shipping.
- **US3 (P2)** — after Foundational (it reads `products.sub_location`, added by T002). Independent of US1/US2.
- **US4 (P3)** — after Foundational. Its suggestions come from US3, but the story's own value (recording and displaying a sub-location) stands without it.

### File-level conflicts to sequence

| File | Tasks | Note |
|---|---|---|
| `tests/unit/test_catalog_service.py` | T009, T015, T032 | Same file across three stories — never in parallel |
| `app/catalog_service.py` | T011, T016, T017, T033 | Same file — sequence |
| `app/product/routes.py` | T012, T018, T034 | Same file — sequence |
| `app/templates/product/categories.html` | T013, T020 | T020 after T013 |
| `app/templates/product/_form_fields.html` | T027, T035 | T035 after T027 |
| `tests/unit/test_vocabulary.py` | T025, T026 | T026 after T025 |

### Parallel opportunities

- **Phase 2**: T005, T006, T007 together (after T002–T004, or alongside them — they touch neither the model nor the migration)
- **US1**: T008 and T009 together (different test files), before their implementations
- **US3**: T027, T028, T029, T030 all together — four disjoint template file sets
- **Phase 7**: T038 and T040 together

### Within each story

Tests are written before the implementation they cover and should fail first. Pure utils before services; services before routes; routes before templates; e2e last, once there is something to drive.

---

## Parallel Example: User Story 3 templates

```bash
# Four disjoint file sets — safe to run together:
Task: "Wrap #location and add its dropdown in app/templates/product/_form_fields.html"
Task: "Include field-autocomplete.js in app/templates/product/add.html and edit.html"
Task: "Vendor dropdown + script in app/templates/product/purchase_add.html"
Task: "Vendor dropdown + script in app/templates/product/capture.html"
```

---

## Implementation Strategy

### MVP — User Story 1 only

1. Phase 1 (T001) — baseline
2. Phase 2 (T002–T007) — schema and shared rename UI
3. Phase 3 (T008–T014) — category rename
4. **Stop and validate** against the US1 section of `quickstart.md`, especially the refusals
5. Ship. A misspelled category is now a one-action fix instead of N product edits — which is SC-001, the issue's headline complaint.

### Incremental delivery

1. Setup + Foundational → schema reversible, shared modal ready
2. + US1 → **MVP**, categories repairable
3. + US2 → tags repairable and mergeable; both P1s done
4. + US3 → the two halves stop drifting apart by spelling
5. + US4 → product sub-location closes the last gap

Each step is a complete increment and none breaks the previous one.

### Single-developer ordering

The parallel markers describe what *could* run concurrently. Working alone, take the phases in order — the file-conflict table above is the only thing that would otherwise bite, and following the phase order avoids all of it.

---

## Notes

- `[P]` means different files and no incomplete dependency — check the conflict table before trusting it
- Commit per task or per logical group; the branch is `issues/61`
- Never invoke `pytest` directly (Constitution IV) — everything goes through `nox`
- `nox -s e2e` needs a 15-minute timeout **set on the Bash tool**, not on the command line
- No `page.wait_for_timeout` or `time.sleep` in `tests/e2e/` — see CLAUDE.md's "Writing e2e tests"
- The whole feature must satisfy the definition of done in `quickstart.md` before the PR opens
