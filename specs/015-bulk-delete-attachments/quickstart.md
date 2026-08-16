# Quickstart / Validation: Delete Several Product Photos at Once

**Feature**: `specs/015-bulk-delete-attachments` | **Date**: 2026-08-16

How to prove this feature works. Automated first, then the handful of things a browser test cannot
see.

## Prerequisites

Use the repository virtualenv by path — do not activate it — and put Python 3.13 on `PATH` for nox:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
```

Docker must be running for the E2E session (MariaDB container).

## Automated checks

```bash
# Unit suite — must stay green. This feature adds no Python, so nothing here should change.
venv/bin/nox -s tests

# E2E — the actual coverage for this feature. Allow 15 minutes.
venv/bin/nox -s e2e
```

The E2E session takes roughly 8–9 minutes warm; give whatever runs it **at least a 15-minute
timeout** (constitution, Principle IV). It must leave the working tree clean — if `git status` is
dirty afterwards, a screenshot test leaked into the run.

Targeted runs while iterating (still through nox — never bare `pytest`):

```bash
venv/bin/nox -s e2e -- tests/e2e/test_product_attachments.py
venv/bin/nox -s e2e -- tests/e2e/test_photo_upload.py
```

## Screenshots (required before merge)

This feature changes `app/templates/**` and `app/static/js/**`, so documentation screenshots must be
regenerated and committed:

```bash
venv/bin/nox -s screenshots_headless
venv/bin/nox -s screenshots_verify
git status docs/images/screenshots/
```

Expect `user-manual/photo_gallery.png` to change — the item photo gallery's header gains the
select-all. The product detail page is not in `tests/e2e/screenshot_config.yaml`, so Stories 1–2
should move no image. See `research.md` §9.

## Scenarios the automated tests cover

Each maps to acceptance scenarios in [spec.md](./spec.md); selectors are fixed in
[contracts/README.md](./contracts/README.md).

**Product Attachments grid** — `tests/e2e/test_product_attachments.py`

1. A product with several attachments shows a checkbox on every tile, and nothing is selected
   (FR-001, US1-1).
2. "Delete Selected" is disabled until something is ticked, and reports the count once it is
   (FR-003, FR-004, US1-2, US1-3).
3. Ticking three and deleting asks for confirmation **once**, naming three; confirming removes
   exactly those three and leaves the rest (FR-005, FR-006, US1-4, US1-5).
4. Dismissing the confirmation deletes nothing and leaves the three ticked (FR-007, US1-6).
5. Select-all ticks every tile; pressing it again clears them (FR-002, US2-1, US2-2).
6. Select-all then delete empties the grid and shows `#no-attachments` (FR-014, US2-3).
7. Ticking two by hand and then using select-all keeps those two ticked and adds the rest
   (US2-4).
8. Ticking a tile's checkbox does not open the full-size image (edge case).
9. A single attachment reads `Delete 1 attachment?`, not `1 attachment(s)` (edge case).
10. The per-tile trash button still deletes just that one, with no confirmation, exactly as before
    (FR-012).

**Item photo gallery** — alongside the existing photo tests

11. Selecting four photos and pressing "Delete Selected" prompts once, names four, and removes all
    four with no further prompts (FR-015, US3-1).
12. Dismissing that prompt deletes nothing (US3-2).
13. Select-all ticks every photo; again clears them (FR-016, US3-3).
14. A read-only gallery offers neither select-all nor "Delete Selected" (FR-016, US3-4).
15. A single photo's own delete button still confirms for that one photo (FR-017, US3-5).

### Notes for whoever writes these

Seed with `live_server.add_test_products([...])` and attach images through the synthetic
`ClipboardEvent` helper already in `tests/e2e/test_product_attachments.py` — driving the file picker
N times is what makes a suite slow.

Drive `window.confirm` with `page.once('dialog', ...)`, as `test_move_items_sub_location.py` does.
Asserting the *count* of dialogs is the point of scenarios 3 and 11: register a handler that records
each dialog's message, then assert one message with the right number in it. `page.on` (not `once`)
is what catches an unwanted second prompt — with `once`, a second prompt would hang the page instead
of failing the assertion, which is a worse failure to diagnose.

Wait on state, never on a duration (`CLAUDE.md`). The all-succeeded path reloads the page, so
`expect(page.locator(CARDS)).to_have_count(n)` is the completion signal and cannot be true before the
batch finished. For the negative assertions — "these two are gone" — establish the grid with a
positive `expect` first; `count()` against a page mid-reload reads zero and passes trivially.

## By hand — what the automated tests cannot show

1. **The partial-failure path.** Reachable only by making one delete fail. Stop the database, or
   delete an attachment row out from under the page, then bulk-delete a selection containing it.
   Expect: the deletable ones disappear, the failed one stays, `#attachment-alerts` says the
   deletion did not fully succeed, and the page does **not** reload (FR-008, FR-009).
2. **The second-tab case.** Open one product in two tabs, delete an attachment in tab A, then select
   it among others in tab B and delete. Expect no error — the already-gone one counts as removed
   (FR-010).
3. **That it is actually pleasant.** Capture a listing that over-collects (issue #96's motivating
   case), then prune it: select-all, untick the two or three worth keeping, delete, confirm. It
   should be one pass and one page reload. If it still feels like a chore, the feature missed.
4. **Touch targets.** The product page's controls are meant to be usable with a thumb (FR-036 /
   SC-010 of the catalog spec). Check the new checkboxes on a phone-width viewport — a checkbox
   crammed against a filename is not a touch target.
