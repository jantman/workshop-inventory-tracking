---

description: "Task list for feature 005 — Structured Specifications"
---

# Tasks: Structured Specifications

**Input**: Design documents from `specs/005-structured-specifications/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Branch**: `issues/71`

**Tests**: Included, and **not optional here**. Constitution IV requires that "changes that alter behavior MUST land with tests covering that behavior", and every task below alters behavior. Coverage is *not* a target — write the test that would have caught the bug, and stop.

**Organization**: Grouped by user story so each ships and is validated on its own. The foundational phase is unusually large for this feature because a column becoming a table is not divisible: nothing renders, filters or suggests until the table exists and the service speaks lists.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1–US3)
- Every task names the exact file it touches

## Path Conventions

Existing repository layout, unchanged. Application code in `app/`, tests in `tests/unit/` and `tests/e2e/`, migrations in `migrations/versions/`. There is no `src/`.

---

## Phase 1: Setup

**Purpose**: Know that anything that breaks later, this feature broke.

- [X] T001 Establish a green baseline on `issues/71` before changing anything: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and `nox -s e2e` (15-minute tool timeout). Record any pre-existing failure rather than silently inheriting it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The table, the migration, and the service semantics every user story sits on. T008 is here rather than in US2 because leaving it undone makes `search_products` raise `AttributeError` on every call — the catalogue list page stops working the moment T002 lands.

**⚠️ CRITICAL**: No user story work begins until T002–T010 are done.

- [X] T002 Add the `ProductSpecification` model to `app/database.py` after `ProductIdentifier` — `id`, `product_id` FK to `products.id` `ondelete='CASCADE'` (indexed), `name String(100)` not-null and indexed, `value Text` not-null, `display_order Integer` not-null. **No `UniqueConstraint('product_id','name')`** and **no `date_added`**; both omissions are argued in [data-model.md](./data-model.md#the-new-table). Replace `Product.specifications = Column(Text)` (line 841) with the relationship — `cascade='all, delete-orphan'`, `passive_deletes=True`, `order_by='ProductSpecification.display_order'` — and change the `to_dict` entry (line 963) to emit a list of `{'name','value'}` in display order.
- [X] T003 [P] Create the Alembic revision `migrations/versions/b1a0c0d10007_structured_product_specifications.py`, `down_revision = 'b1a0c0d10006'`. `upgrade()`: create the table with both indexes, copy every non-blank `products.specifications` into one row named `Specifications` with `display_order` 0, drop the column. `downgrade()`: re-add the column, rebuild each product's text (a lone `Specifications` row restores as the bare paragraph; anything else joins as `name: value` lines in `display_order`), drop the table with indexes and FK first per `b1a0c0d10003`'s downgrade ordering. **Both data steps run as Python loops over `op.get_bind()` with bound parameters** — `GROUP_CONCAT` ordering is spelled differently on MariaDB and SQLite and this is the wrong place to maintain two spellings ([research.md](./research.md#the-migrations-data-step)).
- [X] T004 Exercise the revision against **MariaDB**, following [quickstart.md](./quickstart.md#the-migration-round-trip) exactly — seed products A–D first (including B, whose paragraph contains a colon *and* a newline), then `db upgrade`, `db downgrade b1a0c0d10006`, `db upgrade`, checking the table contents and `DESCRIBE products` at each step rather than trusting the exit code. Use the explicit revision id: `db downgrade -1` fails with `Error: No such option '-1'` in this Flask-Migrate CLI. Constitution V requires the downgrade to have been run, and **no automated test covers this revision** — both suites use `Base.metadata.create_all`.
- [X] T005 Add `CatalogService._validate_specifications(entries)` to `app/catalog_service.py` per [contracts/catalog-service.md](./contracts/catalog-service.md) — drop fully blank entries, raise `ValidationError` for a half-filled one naming the offender, trim both fields, enforce the 100-char name limit, and refuse a duplicate name. **Duplicate comparison is `name.strip().lower()` in Python, never a query**: the deployed collation also folds accents, and FR-004 speaks only of case and whitespace.
- [X] T006 Change `create_product` and `update_product` in `app/catalog_service.py` to take `specifications` as `Optional[List[Dict[str, str]]]` — create builds rows with `display_order` from the surviving list index inside the existing transaction; update replaces the whole set when the key is present and leaves it alone when absent. Remove `'specifications'` from the scalar `_clean` loop at line 493 while leaving it in the `editable` set.
- [X] T007 Add `selectinload(Product.specifications)` to the eager loads in `get_product` (line 199), `search_products` and `list_products` in `app/catalog_service.py`. Without this the detail page and every `to_dict` raise `DetachedInstanceError` — and the unit tests, which stay inside a live session, will not tell you.
- [X] T008 Replace `Product.specifications.like(pattern)` in `search_products`'s free-text branch (line 265) with `Product.specifications.any(or_(ProductSpecification.name.like(pattern), ProductSpecification.value.like(pattern)))` in `app/catalog_service.py` (FR-017). The old line raises `AttributeError` against a relationship, so this is what keeps the catalogue list page alive.
- [X] T009 Unit tests for T005–T008 in `tests/unit/test_catalog_service.py`: create with a list; update replaces wholesale; update without the key leaves rows untouched; blank row dropped; each half-filled row refused; duplicate name refused case-insensitively; `display_order` follows list order with no gap after a dropped blank; and a refusal leaves the product's *other* fields unchanged too.
- [X] T010 [P] Update the existing unit tests that pass the old string kwarg — `tests/unit/test_catalog_service.py` lines 50/56, `tests/unit/test_product_search.py` lines 26/33 — plus the `to_dict` shape assertion in `tests/unit/test_product_model.py` and the stale docstring at `tests/unit/test_capture.py:216`.

**Checkpoint**: `nox -s tests` green. The table exists, the migration round-trips, the service speaks lists. Nothing is visible in the UI yet.

---

## Phase 3: User Story 1 — Record specifications as named values (Priority: P1) 🎯 MVP

**Goal**: The operator records specifications as name/value rows and the product page lays them out as fields. Existing paragraphs are still there, whole.

**Independent Test**: Create a product with three named specifications, view it, and confirm each name and value is its own field in entry order; then open a product created before the migration and confirm its original text is present character for character.

### Implementation for User Story 1

- [X] T011 [US1] Rewrite `_form_product_fields` in `app/product/routes.py` (line 49) to build the specification list from `request.form.getlist('spec_name')` and `getlist('spec_value')`, paired with `zip` — not an index walk, which could raise if the lists ever differ in length. Pass the list straight to the service; the service is what validates it. Leave the ECIA prefill and note block untouched.
- [X] T012 [US1] Replace the specifications textarea in `app/templates/product/_form_fields.html` (lines 34–36) with a rows container, one row per existing specification (each a `spec_name` / `spec_value` pair plus a remove button), an "Add specification" button with a stable id, and a hidden `<template>` row. Every row uses the *same* field names, so no index bookkeeping and no renumbering on removal.
- [X] T013 [US1] Create `app/static/js/product-specifications.js` — a plain IIFE matching `catalog-suggestions.js`. Clone the template on add, remove a row on click, keep at least one blank row present. Datalist wiring comes in US3; this task is rows only.
- [X] T014 [P] [US1] Include `product-specifications.js` in `app/templates/product/add.html` (after line 120) and `app/templates/product/edit.html` (after line 52), and change `edit.html`'s `values` mapping (line 19) to pass the product's specification rows rather than a string.
- [X] T015 [US1] Replace the paragraph in `app/templates/product/detail.html` (lines 95–101) with a `<dl>` rendering each name and value in display order, keeping the card omitted entirely when the list is empty. Keep the `#product-specifications` id on the container so the e2e selectors have an anchor. The per-entry filter link is US2's T024.
- [X] T016 [US1] Teach `app/static/js/product-form.js` about repeated field names: `collect()` stores an array when a name appears more than once, and `apply()` clicks the add-row button until the row count matches before assigning positionally. Without this, restoring a draft silently keeps only the last specification row — and FR-035 is an existing feature with an existing test.

### Tests for User Story 1

- [X] T017 [P] [US1] Update the e2e tests that fill `#specifications`: the `specifications=` kwarg and `#product-specifications` assertion in `tests/e2e/test_product_crud.py` (lines 31, 38), the `create_product` helper in `tests/e2e/test_product_search.py` (lines 13–34), and the call in `tests/e2e/test_wedge_scan.py` (line 40).
- [X] T018 [P] [US1] Rewrite `tests/e2e/test_draft_persistence.py` for repeating rows (lines 26, 36) — fill three specification rows, interrupt, restore, and assert **all three** come back with their names, values and order. Asserting only the first would pass against the bug T016 exists to prevent.
- [X] T019 [US1] Create `tests/e2e/test_product_specifications.py` with the US1 cases: three-row round-trip in entry order; edit changes/removes/adds a row; a product with no specifications shows no card; each refusal (duplicate name differing only in case, name without value, value without name) re-renders with a message and saves nothing; a fully blank row alongside good ones saves without complaint; and `Volt` plus `Vôlt` on one product both save — the case a unique constraint would have broken. Seed with `live_server.add_test_products` except where the form is the subject.

**Checkpoint**: US1 is independently usable. Specifications are named values, laid out as fields, and nothing written before this change was lost.

---

## Phase 4: User Story 2 — Find every product with a given specification (Priority: P2)

**Goal**: "Show me every 12 V converter I own" is one filter, and its result excludes the product that merely mentions 12 V.

**Independent Test**: Seed one product with `Voltage`/`12 V`, one with `Voltage`/`5 V`, and one whose description says "12 V input" but records no voltage. Filter name `Voltage` value `12 V` and get exactly the first.

### Implementation for User Story 2

- [X] T020 [US2] Add `spec_name` and `spec_value` parameters to `search_products` in `app/catalog_service.py` per [contracts/catalog-service.md](./contracts/catalog-service.md) — `Product.specifications.any(...)` using the existing `.any()` tag-filter idiom, with `func.lower(ProductSpecification.name) == spec_name.strip().lower()` for the name (**`func.lower`, not `==`** — SQLite's `==` is case-sensitive and FR-015 is not) and an escaped `.like('%…%')` for the value. A value with no name adds no clause.
- [X] T021 [P] [US2] Unit tests in `tests/unit/test_product_search.py`: name-only returns every value; name plus value narrows; a partial value matches (contained, not exact); a value without a name is ignored rather than raising; the description-only product is excluded; combination with `category`, `tag`, `stock` and `query` narrows together; and free-text search still reaches a word that appears only in a specification value.
- [X] T022 [US2] Pass `spec_name` and `spec_value` through both search routes in `app/product/routes.py` — the `/products` page handler (line ~105, echoing them into `filters` so the form redisplays them) and `/api/products/search`.
- [X] T023 [P] [US2] Add the specification name and value filter inputs to `app/templates/product/search.html`'s filter card (lines 26–70), sized to fit the existing row.
- [X] T024 [US2] Link each specification on `app/templates/product/detail.html` to `/products?spec_name=…&spec_value=…` (FR-018). Depends on T015 — same file, same block.
- [X] T025 [US2] Add the US2 cases to `tests/e2e/test_product_specifications.py`: the three-product discrimination above; name-only filter; **a lower-case name filter matching a capitalised name** (FR-015 — invisible to the unit suite, since SQLite collates BINARY); contained-value match; combination with a category filter; an unrecorded name returning an empty list rather than an error; and following a link from the detail page landing on the filtered catalogue.

**Checkpoint**: SC-001 is met — the question the feature exists to answer is answerable.

---

## Phase 5: User Story 3 — Keep specification names consistent (Priority: P3)

**Goal**: Names and values already in use are offered while typing, on the forms and on the filter, without ever restricting what can be typed.

**Independent Test**: Record `Voltage` on one product, type `Vol` in a second product's specification name and see `Voltage` offered; accept it and see the values recorded under `Voltage` offered for the value.

### Implementation for User Story 3

- [X] T026 [US3] Add `list_specification_names(prefix=None)` and `list_specification_values(name, prefix=None)` to `app/catalog_service.py`, beside `list_tags` (line 1235) and `list_categories`. **Dedupe case-insensitively in Python, not with `SELECT DISTINCT`** — DISTINCT folds under the deployed collation and does not under SQLite, which is why `VocabularyService._rank_and_dedupe` already works this way. A blank or unrecorded name returns `[]`.
- [X] T027 [P] [US3] Unit tests for both readers in `tests/unit/test_catalog_service.py`: names in use, prefix narrowing, values scoped to one name, a blank name returning `[]`, and an unrecorded name returning `[]`.
- [X] T028 [US3] Add `GET /api/specification-names` and `GET /api/specification-values` to `app/product/routes.py`, modelled on `api_categories` / `api_tags` (lines 672–689) and shaped per [contracts/http-routes.md](./contracts/http-routes.md). A missing or unrecorded `name` returns `200` with an empty list, not `400` — the operator is mid-word.
- [X] T029 [US3] Add the shared name `<datalist>` to `app/templates/product/_form_fields.html` and `app/templates/product/search.html`, with every name input carrying `list=`, and a per-row value datalist in the form's row template.
- [X] T030 [US3] Extend `app/static/js/product-specifications.js` to fill the shared name datalist once on load and refill a row's value datalist when that row's name changes, plus the same pair on the search filter. Plain `<datalist>`, **not `FieldAutocomplete`** — that component is constructed per DOM id and these rows are cloned at runtime; a datalist also cannot restrict entry, so FR-021 holds by construction ([research.md](./research.md#client-side-datalists-not-fieldautocomplete)).
- [X] T031 [US3] Add the US3 cases to `tests/e2e/test_product_specifications.py`: a name suggestion offered from another product; value suggestions scoped to the entered name; changing a row's name changing its value suggestions; a brand-new name and value accepted anyway (FR-021); the same name recorded in two cases yielding **one** suggestion (FR-019 — the second case the unit suite cannot prove); and the same names offered on the filter. Wait with `expect(datalist.locator('option')).to_have_count(n)` — options are appended after the fetch resolves, so that is a complete signal (CLAUDE.md pattern C).

**Checkpoint**: All three stories done. The vocabulary now degrades slowly rather than immediately.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 Confirm the three collation-sensitive assertions actually bite: temporarily make the duplicate check (T005), the name filter (T020) and the suggestion dedup (T026) case-**sensitive**, one at a time, and confirm the corresponding e2e case in `tests/e2e/test_product_specifications.py` fails each time. This is the discipline `091e918` established after the same gap deleted a tag and every one of its associations; `nox -s tests` passes either way and always would.
- [X] T033 [P] Regenerate documentation screenshots — `nox -s screenshots_headless` then `nox -s screenshots_verify` — and commit the images with the change. `app/templates/product/**` and `app/static/js/**` both changed, so CI blocks merge without this.
- [X] T034 Run the full suites and confirm the working tree is clean afterwards: `nox -s tests`, then `nox -s e2e` with a 15-minute tool timeout, then `git status`.
- [X] T035 Walk the manual validation in [quickstart.md](./quickstart.md#manual-validation) — all three stories plus the draft-persistence regression — and confirm every item in its definition of done, including that the migration round-trip of T004 was actually performed and checked rather than assumed.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001)** — first.
- **Foundational (T002–T010)** — blocks everything. T002 before T003–T010; T003 before T004; T005 before T006; T006–T008 before T009.
- **US1 (P1)** — after Foundational. The MVP.
- **US2 (P2)** — after Foundational. Independent of US1 except T024, which edits the block T015 creates.
- **US3 (P3)** — after Foundational. Its form-side wiring (T029, T030) edits files US1 creates, so in practice it follows US1.
- **Polish** — after all three.

### File-level conflicts to sequence

| File | Tasks | Note |
|---|---|---|
| `app/catalog_service.py` | T005, T006, T007, T008, T020, T026 | Same file across all phases — never in parallel |
| `app/product/routes.py` | T011, T022, T028 | Same file — sequence |
| `tests/unit/test_catalog_service.py` | T009, T010, T027 | Same file — sequence |
| `tests/unit/test_product_search.py` | T010, T021 | T021 after T010 |
| `app/templates/product/detail.html` | T015, T024 | T024 after T015 |
| `app/templates/product/_form_fields.html` | T012, T029 | T029 after T012 |
| `app/templates/product/search.html` | T023, T029 | Sequence — different regions, same file |
| `app/static/js/product-specifications.js` | T013, T030 | T030 extends T013 |
| `tests/e2e/test_product_specifications.py` | T019, T025, T031 | One file, three stories — sequence |

### Parallel opportunities

- **Foundational**: T003 alongside T002's non-model work; T010 alongside T009 (different assertions, but same file for part of it — check the table)
- **US1**: T014, T017, T018 together — three disjoint file sets
- **US2**: T021 and T023 together (unit tests and a template)
- **US3**: T027 alongside T028
- **Polish**: T033 alongside T032

### Within each story

Service before routes; routes before templates; templates before the JS that drives them; e2e last, once there is something to drive. T016 is the exception — it belongs with the form work, not the tests, because T018 is what proves it.

---

## Implementation Strategy

### MVP — User Story 1 only

1. Phase 1 (T001) — baseline
2. Phase 2 (T002–T010) — table, migration, service semantics
3. Phase 3 (T011–T019) — the form, the display, draft persistence
4. **Stop and validate** against the US1 section of `quickstart.md`, especially the pre-migration product's paragraph surviving character for character
5. Ship. Specifications are named values laid out as fields, and nothing is lost.

Filtering is what the feature is *for*, so the MVP is genuinely incomplete without US2 — but US1 alone is safe to sit on, because the irreversible part (the migration) is already behind you and the product page is already more legible than the paragraph it replaced.

### Incremental delivery

1. Setup + Foundational → the shape changed, the data carried across, unit suite green
2. + US1 → **MVP**, records and displays named values
3. + US2 → SC-001 met; the 12 V question is answerable
4. + US3 → the vocabulary stops degrading

Each step is a complete increment and none breaks the previous one.

### Single-developer ordering

The parallel markers describe what *could* run concurrently. Working alone, take the phases in order — `app/catalog_service.py` is touched by six tasks across four phases, and following the phase order avoids every conflict in the table above.

---

## Notes

- `[P]` means different files and no incomplete dependency — check the conflict table before trusting it
- Commit per task or per logical group; the branch is `issues/71`
- Never invoke `pytest` directly (Constitution IV) — everything goes through `nox`
- `nox -s e2e` needs a 15-minute timeout **set on the Bash tool**, not on the command line
- No `page.wait_for_timeout` or `time.sleep` in `tests/e2e/` — see CLAUDE.md's "Writing e2e tests"
- T004 is the one task in this feature that can destroy data. Do it deliberately, on seeded rows you have recorded, and check the results rather than the exit code.
- The whole feature must satisfy the definition of done in `quickstart.md` before the PR opens
