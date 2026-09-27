# Tasks: Tool, Chemical and Mechanical Categories in the Default Taxonomy

**Input**: `specs/055-tool-taxonomy/` (spec.md approved 2026-09-27, plan.md, research.md, data-model.md, quickstart.md)

**Tests**: The existing shape and record-agreement tests in `tests/unit/test_catalog_taxonomy.py` cover the new data. One probe test is added.

## Phase 1: Setup

No setup is needed; every file already exists.

## Phase 2: Foundational

- [X] T001 Update `ROOTS` in `tests/unit/test_catalog_taxonomy.py` to the six approved roots: `fasteners`, `electrical`, `electronics`, `tools`, `adhesives & chemicals`, `mechanical`. It is both the parser's heading list and the agreed-roots assertion.

## Phase 3: User Story 1 - Approve the proposal (P1)

- [X] T002 [US1] Record the owner's approval, the removal of `tools/taps & dies/wrenches & die stocks`, and the settled open questions in `specs/055-tool-taxonomy/spec.md`.

## Phase 4: User Story 2 - File a tool into an unoccupied branch (P2)

**Independent test**: On an empty catalog the new branches and keys are offered (`tests/unit/test_catalog_taxonomy.py` probe; `tests/e2e/test_category_taxonomy.py` unchanged and green).

- [X] T003 [US2] Add the 124 approved paths to `DEFAULT_CATEGORY_PATHS` in `app/utils/catalog_taxonomy.py`. Use the spec's tables: the 3 roots, their subtrees, and 6 `fasteners/pins & clips/*` leaves. Keep the tuple `sorted()`; generate the order mechanically.
- [X] T004 [US2] Add the 35 approved keys to `DEFAULT_SPECIFICATION_KEYS` in `app/utils/catalog_taxonomy.py`, keeping it sorted.
- [X] T005 [US2] (No change needed: the docstring makes no three-root claim.) Update the module docstring and comments in `app/utils/catalog_taxonomy.py` wherever they state the defaults' scope. There must be no stale "three roots" claim.
- [X] T006 [US2] Add a probe test class to `tests/unit/test_catalog_taxonomy.py`. It asserts that each spec User Story 3 probe branch is in `DEFAULT_CATEGORY_PATHS`, that `tools/taps & dies/wrenches & die stocks` is absent, and that `Chamfer`, `Length Series` and `Shank` are in `DEFAULT_SPECIFICATION_KEYS`.

## Phase 5: User Story 3 - The record says where things go (P3)

- [X] T007 [US3] In `docs/category-taxonomy.md`, rewrite **Scope** to list the six settled roots and what stays deferred: hand and power tools, general DIY, 3D printing, automotive diagnostics. Add the seam statements for the new roots.
- [X] T008 [US3] In `docs/category-taxonomy.md`, change the `fasteners` table. Edit the `pins & clips` row to drop the "out of scope" note. Add the six `pins & clips/*` rows. Widen the `rivets` row to cover solid rivets.
- [X] T009 [US3] In `docs/category-taxonomy.md`, add `## tools`, `## adhesives & chemicals` and `## mechanical` sections. Each gets a one-line intro and a `| \`relative path\` | what belongs |` table, exactly the shape `_record_branches()` parses. Rows are relative to the root.
- [ ] T010 [US3] In `docs/category-taxonomy.md`, add the new branch families to the registry table under `## Specification keys`. Add a `### Key meanings` table after it, so the parser stops before the example values. Add the new vendor-name normalization rows.
- [X] T011 [US3] In `docs/category-taxonomy.md`, add the approved probes to **The three probes**, retitled **Probes**. Update **What deliberately has no branch**: dielectric grease now has a home; hand tools, including tap wrenches and die stocks, stay deferred.

## Phase 6: Polish

- [X] T012 Run `nox -s tests` and `nox -s e2e -- tests/e2e/test_category_taxonomy.py tests/e2e/test_product_specifications.py`.
- [X] T013 Regenerate screenshots with `nox -s screenshots_headless`. Measure baseline churn first. Commit only files this feature changed (expected: `docs/images/screenshots/user-manual/category_tree.png`). Run `nox -s screenshots_verify`.
- [ ] T014 Run the full `nox -s e2e` detached, and confirm it is green.
- [X] T015 Run the spelling check `grep -ric catalogue README.md docs/ app/ tests/`; it must return nothing.

## Dependencies

- T001 comes before T012.
- T003 through T006 and T007 through T011 are independent in files, but T012 needs both done, because the agreement test fails until module and record match.
- T013 and T014 follow T012.

## Parallel opportunities

- The module edits (T003 to T005) and the record edits (T007 to T011) touch different files, and can be done in parallel.

## Implementation strategy

A single increment. The agreement test makes the module-only and record-only halves each red on their own, so they ship together.
