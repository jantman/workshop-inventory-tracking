# Research: Delete Several Product Photos at Once

**Feature**: `specs/015-bulk-delete-attachments` | **Date**: 2026-08-16

Everything this feature touches already exists. The research below is about what *not* to build as
much as what to build, so each entry records the decision, why, and what was rejected.

---

## 1. One bulk endpoint, or a loop over the existing single delete?

**Decision**: Loop over the existing `DELETE /api/attachments/<id>`, from the browser, one request
at a time. **No new route, no new service method, no schema change, no migration.**

**Rationale**: Issue #96 offers both and says "if that is genuinely simpler at this scale" — it is.
A new endpoint costs a route, a service method, request-body validation, a partial-failure response
shape, and unit tests for all of it, to save a handful of round trips on a LAN for a user who does
this occasionally. Constitution Principle I: build for the requirement in front of you, and no
premature optimization without a measurement. There is no measurement here, and no plausible one:
the worst realistic case is a couple of dozen thumbnails.

The existing route also already does exactly the right thing per attachment, including releasing
photo bytes that nothing else references (`PhotoService.delete_attachment`), which is what FR-011
requires. Reimplementing that against a list is how the two paths drift apart.

**Alternatives considered**:

- *`DELETE /api/attachments` with a JSON id list.* Rejected: new surface for no measured benefit,
  and it would need its own partial-failure semantics that the single route already expresses via
  per-request status codes.
- *A `POST /api/products/<id>/attachments/delete` form post with a full page reload.* Rejected: the
  card is already JavaScript-driven for upload, paste and delete; a form post would be a second,
  inconsistent mechanism in the same card.

---

## 2. Sequential requests, not concurrent

**Decision**: `await` each delete before starting the next.

**Rationale**: Two attachments can reference the same photo row (the same image attached twice, or
attached to both a product and a purchase). `PhotoService.delete_attachment` deletes the attachment,
then asks whether any attachment or item association still references the photo, and deletes the
photo bytes if not. Two of those running concurrently in separate sessions can both observe "nothing
else references it" and both try to delete the same `Photo` — one of them fails, and the user sees a
spurious failure for a delete that actually happened. Sequential requests make that unreachable
without any locking, and at this scale cost nothing observable.

This is not the concurrency the issue says not to defend against — that is *multi-user* concurrency,
and there is none. This is self-inflicted concurrency that a `for ... await` simply does not create.
Per Principle I's carve-out, data integrity outranks a micro-optimization nobody asked for.

**Alternatives considered**: `Promise.all` / `Promise.allSettled` over all ids. Rejected for the
above; it is not simpler to write, either.

---

## 3. What happens to the grid after the batch

**Decision**: If every delete succeeded, reload the page — exactly what the existing single delete
does. If any failed, do **not** reload: remove the tiles that were deleted, leave the ones that were
not, and show the failure message in `#attachment-alerts`.

**Rationale**: The reload is the existing, proven refresh path and it makes the empty-state message
(`#no-attachments`) appear for free (FR-014) without duplicating that Jinja markup in JavaScript,
where it would become a second source of truth for the same string. But a reload would also wipe the
failure message FR-009 requires, so the failure path cannot reload — and it does not need to, because
a batch with a failure in it cannot have emptied the grid.

Two short paths, neither of which invents markup. The failure path is the only new DOM manipulation,
and it is one `.remove()` per succeeded tile.

**Alternatives considered**:

- *Always update the DOM, never reload.* Rejected: requires synthesizing the `#no-attachments`
  element in JavaScript, duplicating the template's empty-state text and classes.
- *Always reload, and put the failure message in a query parameter or session flash.* Rejected:
  new plumbing (flash messages are not used by this card) for a rare path.

---

## 4. A 404 counts as success

**Decision**: Treat `404` from the delete route as a successful removal; treat any other non-2xx, or
a network error, as a failure for that attachment.

**Rationale**: FR-010. The route raises `ItemNotFoundError` when the row is gone, which the central
error handlers turn into a 404. "It is not there" is the state the user asked for. The realistic
cause is a second tab, and the honest response is to move on rather than report an error for a
delete that has already happened.

---

## 5. Where the controls go, and what they are

**Decision**: A checkbox on each tile inside the existing `.attachment-row` card. A select-all
checkbox and a "Delete Selected (N)" button in a small toolbar row above the grid, inside the
Attachments card body. Bootstrap 5.3.2 form-check and button classes, no new CSS framework, no new
component.

**Rationale**: Constitution: Jinja2 + Bootstrap 5.3.2 server-rendered UI; introducing a frontend
framework requires amending it. Checkbox + button is what the issue asked for in as many words. The
toolbar row is server-rendered in `product/detail.html` alongside the grid so the markup lives with
the markup, and `product-attachments.js` binds behavior to it — the same division the card already
uses.

The tile checkbox must not sit inside the `<a>` that opens the full image (edge case: ticking must
not navigate). It goes in the card body row that already holds the filename and the trash button.

**Alternatives considered**: A "selection mode" toggle that reveals the checkboxes. Rejected as a
configuration knob for a single-user tool — Principle I.

---

## 6. The confirmation

**Decision**: `window.confirm` with singular/plural wording — `Delete 1 attachment?` /
`Delete 7 attachments?`. Same for the item photo gallery: `Delete 1 photo?` / `Delete 12 photos?`.

**Rationale**: The application already confirms destructive actions with `window.confirm`
(`photo-manager.js` does exactly this, and the E2E suite already drives such dialogs with
`page.once('dialog', ...)`). A modal component would be new machinery for the same yes/no.
The spec's edge case forbids `1 attachment(s)`, so the wording branches on the count.

---

## 7. The item photo gallery (Story 3)

**Decision**: Split the existing `deletePhoto(photo)` into the confirmation and the removal:
`deletePhoto` keeps its own `confirm` and delegates; a new confirmation-free removal helper does the
work; `deleteSelectedPhotos` confirms **once** and then calls the helper for each selected photo.
Add a select-all checkbox to the existing `.gallery-actions` block, which is already omitted when
the gallery is read-only.

**Rationale**: This is the smallest change that satisfies FR-015 through FR-017. Today
`deleteSelectedPhotos` confirms the batch and then calls `deletePhoto` in a loop, which confirms
again for every photo — thirteen prompts to delete twelve. Extracting the removal is the standard fix
and leaves the single-photo path (FR-017) byte-for-byte equivalent in behavior.

Its per-photo success toast becomes one summary toast for the batch, for the same reason the
confirmations collapse: twelve toasts for one action is the same defect wearing a different hat. The
single-photo delete keeps its single toast.

`.gallery-actions` already exists and is already suppressed for a read-only gallery, so the select-all
inherits FR-016's read-only rule by being placed there rather than by a new condition.

**Alternatives considered**: Leaving the item gallery alone. Rejected — the user chose to include it
during specification, and issue #96 names it.

---

## 8. Testing approach

**Decision**: E2E (Playwright) only. No new unit tests, because no Python changes.

**Rationale**: Every change in this feature is in `app/templates/product/detail.html`,
`app/static/js/product-attachments.js` and `app/static/js/photo-manager.js`. The constitution
requires behavior changes to land with tests covering that behavior and explicitly refuses coverage
percentage as a goal — "write the test that would have caught the bug, and stop". The behavior here
is browser behavior; a unit test cannot see it.

`tests/e2e/test_product_attachments.py` already seeds a product with `live_server.add_test_products`
and attaches images with a synthetic `ClipboardEvent`, which is the fastest way to get N attachments
onto a product without driving a file picker N times. New selection tests extend that file. The item
gallery tests go alongside the existing photo tests.

Waiting follows `CLAUDE.md`: the full-success path reloads the page, so `expect(CARDS)` polling to
the new count is the signal (pattern C — the rendered state cannot predate the completed batch); the
partial-failure path removes tiles after `await`, so the same holds. No `wait_for_timeout`.

---

## 9. Screenshots

**Decision**: Regenerate documentation screenshots and commit them with the change.

**Rationale**: The constitution's Development Workflow section requires it for any change to
`app/templates/**` or `app/static/js/**`, and CI blocks merge on stale screenshots. Run
`nox -s screenshots` (or `screenshots_headless`), then `nox -s screenshots_verify`.

What actually moves is worth knowing in advance. The product detail page is **not** in
`tests/e2e/screenshot_config.yaml`, so Stories 1–2 change no documented image. Story 3 does: the
item photo gallery appears in `photo_gallery` (`user-manual/photo_gallery.png`) and
`photo_upload_interface`, and the new select-all sits in the gallery header those capture. Expect
`user-manual/photo_gallery.png` to change and commit it with the rest.

Documentation prose is the other half: `docs/user-manual.md`'s "Photo Management" section describes
the gallery, and its figures are captioned from this config. If it describes deleting photos one at
a time, it needs a sentence about the selection. Nothing in `docs/` covers the product Attachments
card's controls today, so Stories 1–2 add a short paragraph where the catalog documentation covers
attachments, or none if it does not describe the card's controls either.
