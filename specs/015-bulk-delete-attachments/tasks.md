---

description: "Task list for feature implementation"
---

# Tasks: Delete Several Product Photos at Once

**Input**: Design documents from `/specs/015-bulk-delete-attachments/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/README.md](./contracts/README.md), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are **included and required**, not optional. Constitution Principle IV: "Changes
that alter behavior MUST land with tests covering that behavior." Every change here is browser
behavior, so the coverage is E2E — see [research.md](./research.md) §8 for why there are no new unit
tests.

**Organization**: Tasks are grouped by user story so each can be implemented, tested and shipped on
its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are in every task

## Path Conventions

Flask web application, server-rendered. This feature lives entirely in `app/templates/`,
`app/static/js/` and `tests/e2e/`. **No Python is changed** — if a task has you editing
`app/product/routes.py`, `app/photo_service.py` or anything under `migrations/`, stop and re-read
[research.md](./research.md) §1.

---

## Phase 1: Setup

**Purpose**: Nothing to scaffold — the feature adds no dependency, no module and no configuration.

- [ ] T001 Confirm work is on feature branch `issues/96`, not `main` (constitution: non-trivial code changes go through a branch and a PR)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: none.

**There are no foundational tasks.** This is a deliberate finding, not an omission: the backend
already does everything this feature needs (`DELETE /api/attachments/<id>` and
`PhotoService.delete_attachment` handle one attachment correctly, including releasing orphaned photo
bytes), and there is no shared new module for the stories to build on. US1 and US3 touch disjoint
files and can both start immediately.

**Checkpoint**: User story implementation can begin.

---

## Phase 3: User Story 1 - Prune an over-captured gallery (Priority: P1) 🎯 MVP

**Goal**: Tick several attachments in the product Attachments card, press delete once, confirm once,
and have exactly those attachments removed.

**Independent Test**: Open a product with several attachments, tick four, press "Delete Selected",
confirm the single prompt naming four — exactly those four are gone and the rest are untouched.

### Tests for User Story 1

> Write these first. They will fail against the current page, which has no selection controls at all.

- [ ] T002 [US1] E2E: selection controls exist and drive the button — every tile has a `.attachment-select` checkbox with nothing selected initially; `#delete-selected-attachments` is `disabled` at zero selected and reports the count once tiles are ticked (FR-001, FR-003, FR-004; quickstart scenarios 1–2) in `tests/e2e/test_product_attachments.py`
- [ ] T003 [US1] E2E: **exactly one** confirmation, and cancel deletes nothing — register a `page.on('dialog', ...)` handler that **records every dialog message** so a second prompt fails the assertion rather than hanging the page; assert one message naming the count, that confirming removes exactly the ticked attachments and leaves the rest, and that dismissing removes nothing and leaves the tiles ticked (FR-005, FR-006, FR-007; quickstart scenarios 3–4) in `tests/e2e/test_product_attachments.py`
- [ ] T004 [US1] E2E: edge cases and regression — ticking a checkbox does not navigate to the full-size image; a one-attachment selection reads `Delete 1 attachment?` and never `1 attachment(s)`; the existing `.delete-attachment-btn` still deletes just its own tile with no confirmation (FR-012; quickstart scenarios 8–10) in `tests/e2e/test_product_attachments.py`

### Implementation for User Story 1

- [ ] T005 [US1] Add a `.attachment-select` checkbox carrying `data-attachment-id` to each `.attachment-row` in `app/templates/product/detail.html`, placed in the card-body row beside the filename and trash button — **outside** the `<a>` that wraps the thumbnail, so ticking never opens the image
- [ ] T006 [US1] Add the selection toolbar above `#attachment-list` in `app/templates/product/detail.html`: a `#delete-selected-attachments` button, `disabled` by default, rendered only when the product has at least one attachment (`{% if attachments %}`). Leave `#no-attachments` exactly as it is — it must stay **absent** while attachments exist, because `tests/e2e/test_product_attachments.py` asserts `to_have_count(0)` on it
- [ ] T007 [US1] Wire selection state in `app/static/js/product-attachments.js`: on every checkbox `change`, count the checked boxes, enable/disable `#delete-selected-attachments` and set its label to report the count. Read the selection from the DOM each time — do not keep a parallel array ([data-model.md](./data-model.md))
- [ ] T008 [US1] Implement the bulk delete handler in `app/static/js/product-attachments.js`: confirm **once** with singular/plural wording, disable the button for the duration so a second press cannot start a second loop, then `await` `csrfFetch(DELETE /api/attachments/<id>)` for each selected id **one at a time** (sequential — two attachments can share a photo row; [research.md](./research.md) §2). Treat `204` **and `404`** as removed (FR-010); anything else as failed. With no failures, `window.location.reload()`
- [ ] T009 [US1] Implement the partial-failure path in `app/static/js/product-attachments.js`: when any delete failed, do **not** reload — remove the tiles that were deleted, leave the ones that were not, and report through the existing `showAlert` into `#attachment-alerts` that the deletion did not fully succeed (FR-008, FR-009)

**Checkpoint**: A user can prune a captured gallery in one pass. This is a shippable MVP on its own —
select-all is convenience on top of it.

---

## Phase 4: User Story 2 - Clear the whole capture in one pass (Priority: P2)

**Goal**: A select-all so clearing twenty images does not mean twenty ticks.

**Independent Test**: On a product with several attachments, press select-all, delete, confirm — the
grid ends up empty and shows the "nothing attached" message.

**Depends on**: US1 (T005–T009). The select-all writes to the checkboxes US1 introduces and the
button US1 wires.

### Tests for User Story 2

- [ ] T010 [US2] E2E: select-all ticks every tile and toggles them all off again; select-all then delete empties the grid and makes `#no-attachments` visible; ticking two by hand and then using select-all keeps those two ticked and adds the rest (FR-002, FR-014; quickstart scenarios 5–7) in `tests/e2e/test_product_attachments.py`

### Implementation for User Story 2

- [ ] T011 [US2] Add the `#select-all-attachments` checkbox to the selection toolbar in `app/templates/product/detail.html`, with a visible label
- [ ] T012 [US2] Implement select-all in `app/static/js/product-attachments.js`: checking it ticks every `.attachment-select`, unchecking it clears them, and either way the button state from T007 is refreshed. Keep it honest when individual boxes change — it must not read as "all selected" while one tile is unticked

**Checkpoint**: Both product-grid stories work. The Attachments card is done.

---

## Phase 5: User Story 3 - One confirmation on the item photo gallery too (Priority: P3)

**Goal**: The inventory item photo gallery stops asking N+1 times and gains the select-all it lacks.

**Independent Test**: On the Edit Item form for an item with several photos, press select-all, press
"Delete Selected", answer one prompt — every photo is gone with no further prompting.

**Independent of US1 and US2**: different file (`app/static/js/photo-manager.js`), different page,
different test file. This phase can be worked in parallel with Phases 3–4.

### Tests for User Story 3

- [ ] T013 [P] [US3] E2E for the item photo gallery in a new `tests/e2e/test_photo_bulk_delete.py`: selecting four photos and pressing "Delete Selected" produces **exactly one** dialog naming four and removes all four (record every dialog message, as in T003 — a test that only checks *a* prompt appeared passes against today's N+1 bug); dismissing it deletes nothing; select-all ticks every photo and toggles off; a read-only gallery offers neither select-all nor "Delete Selected"; a single photo's own delete button still confirms for that one photo (FR-015, FR-016, FR-017; quickstart scenarios 11–15)

### Implementation for User Story 3

- [ ] T014 [US3] Extract the removal from `deletePhoto` in `app/static/js/photo-manager.js` into a confirmation-free helper (the `fetch` to `DELETE /api/photos/<id>` when uploaded, the splice out of `this.photos`, the card `.remove()`, `updateGalleryDisplay()`). `deletePhoto` keeps its own `confirm` and calls the helper, so the single-photo path behaves exactly as it does today (FR-017)
- [ ] T015 [US3] Rewrite `deleteSelectedPhotos` in `app/static/js/photo-manager.js` to confirm **once** with singular/plural wording and then call the T014 helper for each selected photo — iterating a **copy** of the selected list, because the helper splices `this.photos` while it runs. Collapse the per-photo success toast into one summary toast for the batch; the single-photo delete keeps its own single toast (FR-015)
- [ ] T016 [US3] Add a `.select-all-photos` checkbox inside the existing `.gallery-actions` block in `app/static/js/photo-manager.js`, setting `photo.selected` and each `.photo-select` checkbox, then calling `updateSelectionActions()`. Placing it in `.gallery-actions` is what satisfies the read-only rule — that block is already omitted when `isReadOnly` (FR-016)

**Checkpoint**: Both grids select and delete the same way.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T017 Update `docs/user-manual.md`: in **Product Attachments** (~line 1023), describe selecting several thumbnails and deleting them in one press with one confirmation; in **Photo Management** (~line 420), which currently does not mention deleting photos at all, describe select-all and "Delete Selected". American spelling — `catalog`, never `catalogue` (CLAUDE.md)
- [ ] T018 Regenerate documentation screenshots — `venv/bin/nox -s screenshots_headless`, then `venv/bin/nox -s screenshots_verify` — and commit what changes. Expect `docs/images/screenshots/user-manual/photo_gallery.png` to move (the gallery header gains the select-all); the product detail page is not in `tests/e2e/screenshot_config.yaml`, so US1/US2 should move no image. Required by the constitution for any change to `app/templates/**` or `app/static/js/**`, and CI blocks merge on stale screenshots
- [ ] T019 [P] Run `venv/bin/nox -s tests` — must stay green. This feature adds no Python, so nothing here should move
- [ ] T020 Run `venv/bin/nox -s e2e` with a **≥15-minute** timeout on the tool running it (constitution Principle IV; the suite takes ~8–9 minutes warm). Then confirm `git status` is clean — a dirty tree means a screenshot test leaked into the run
- [ ] T021 Review the new E2E tests against the checklist in `CLAUDE.md` § "Reviewing a new e2e test": every wait names an element rather than a number; no `wait_for_timeout`, no `time.sleep`, no `networkidle`; every `count()` / `is_visible()` / `get_attribute()` has a positive `expect(...)` establishing the region first; every negative assertion would fail against a page that has not loaded
- [ ] T022 Work through the by-hand list in [quickstart.md](./quickstart.md) — the partial-failure path (make one delete fail), the second-tab already-deleted case, whether pruning a real over-captured gallery actually feels like one pass, and the checkbox touch targets at phone width. These are the four things the browser tests cannot show
- [ ] T023 Open a pull request for `issues/96` referencing issue #96, with `test.yml` green

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: one confirmation, no blockers
- **Foundational (Phase 2)**: empty — nothing blocks the stories
- **US1 (Phase 3)**: can start immediately
- **US2 (Phase 4)**: depends on US1 — it extends US1's toolbar and checkboxes
- **US3 (Phase 5)**: independent of both; can run concurrently with Phases 3–4
- **Polish (Phase 6)**: after whichever stories are being shipped

### Within User Story 1

T002 → T003 → T004 (same test file, written first) → T005 → T006 (same template) → T007 → T008 →
T009 (same JavaScript file). Sequential throughout: every task in this story shares a file with its
neighbor.

### Within User Story 2

T010 (test) → T011 (template) → T012 (JavaScript).

### Within User Story 3

T013 (test, its own new file) → T014 → T015 → T016 (all `photo-manager.js`, and T015 depends on the
helper T014 extracts).

### Parallel Opportunities

This is a small feature and there is little to parallelize honestly — most tasks in a story share a
file with the task before them. What genuinely can run at the same time:

- **US3 alongside US1/US2.** Disjoint files: `photo-manager.js` and `test_photo_bulk_delete.py`
  against `detail.html`, `product-attachments.js` and `test_product_attachments.py`. This is the one
  real split.
- **T013** is marked `[P]` because it is the only test task in a file nothing else touches.
- **T019** (`nox -s tests`) is marked `[P]` — it needs no browser and can run while E2E work
  continues.

Everything else in a story is sequential. Marking same-file tasks `[P]` would just produce conflicts.

---

## Parallel Example

```bash
# Two independent tracks, once T001 is confirmed:
Track A (product Attachments card): T002 → … → T012
Track B (item photo gallery):       T013 → T014 → T015 → T016
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001 (branch)
2. T002–T009 — selection, one confirmation, sequential delete, partial-failure path
3. **STOP and VALIDATE**: prune a product's attachments in one pass
4. This alone resolves issue #96's reported pain

### Incremental Delivery

1. US1 → the capture can be pruned in one pass (MVP)
2. US2 → clearing the whole capture takes three actions
3. US3 → the item photo gallery stops asking thirteen times to delete twelve photos
4. Polish → docs, screenshots, full suites, by-hand checks, PR

---

## Notes

- `[P]` = different files, no dependency on an incomplete task
- Commit after each task or logical group
- **The N+1 confirmation bug (US3) needs a test that counts dialogs.** A test asserting only that a
  prompt appeared passes against the current broken behavior — the whole defect is the extra twelve
- **No Python, no migration.** If either appears in a diff, the plan has been misread
- Waiting rules for the new E2E tests are not negotiable style: see `CLAUDE.md` and Principle IV. The
  full-success path reloads, so `expect(locator).to_have_count(n)` is the completion signal
