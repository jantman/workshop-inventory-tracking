# Feature Specification: Delete Several Product Photos at Once

**Feature Branch**: `015-bulk-delete-attachments`

**Created**: 2026-08-16

**Status**: Draft

**Input**: GitHub issue #96 — "Delete several product photos at once": *From the #80 verification pass, comment item 10. `B0FX4PDW6M`'s capture brought in a large number of images of the vendor's other products, and clearing them meant deleting one at a time. #94 is the fix for that particular over-capture. This is the fix for the general case: capture reads page markup, markup changes without warning, and a capture that brings in too much is a normal outcome the design accepts. Pruning it should not be a dozen round trips. Checkbox selection in the product photo grid, a select-all, and one delete for the selection, with a single confirmation naming the count. `app/static/js/product-attachments.js` and `photo-manager.js` are where this lives. Keep it small — one endpoint taking a list of attachment ids, or a loop over the existing single-delete endpoint if that is genuinely simpler at this scale. There is no concurrency to defend against here. The existing single-photo delete stays as it is.*

## Terminology

- **Attachments grid** — the thumbnail grid in the **Attachments** card on a product's detail page.
  This is what the issue calls "the product photo grid". It holds datasheets, diagrams and captured
  listing images alike, and it is where over-capture lands.
- **Attachment** — one tile in that grid: one file attached to the product.
- **Selection** — the set of attachments the user has ticked. Empty until the user ticks something.
- **Item photo gallery** — a *different* grid: the photos on an inventory item, shown on the Add Item
  and Edit Item forms. Related but distinct; see Assumptions for its treatment here.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prune an over-captured gallery (Priority: P1)

A user has captured a product listing and the capture brought in a dozen images, most of which are
the vendor's *other* products. They want to keep two or three and get rid of the rest. Today each
unwanted image costs a separate trash-button press and a separate full page reload — a dozen round
trips to clean up one capture, each one moving the remaining tiles around under the cursor. They want
to tick the ones they do not want, press delete once, confirm once, and be done.

**Why this priority**: This is the whole point of the issue and it is testable end to end on its own.
Shipping only this resolves the reported pain.

**Independent Test**: Open a product whose Attachments grid holds several files, tick four of them,
press the delete action, confirm the prompt that names four, and observe that exactly those four are
gone and the rest are untouched.

**Acceptance Scenarios**:

1. **Given** a product detail page with attachments, **When** the user looks at the Attachments grid,
   **Then** every tile carries a selection control and nothing is selected.
2. **Given** nothing is selected, **When** the user looks for the delete-selection action, **Then**
   it is not available to press.
3. **Given** the user ticks three attachments, **When** they look at the delete-selection action,
   **Then** it is available and reports that three are selected.
4. **Given** three attachments are selected, **When** the user presses the delete-selection action,
   **Then** they are asked to confirm once, and the prompt names the number three.
5. **Given** that confirmation prompt is showing, **When** the user confirms, **Then** exactly those
   three attachments are removed, no further confirmation is asked for, and the remaining
   attachments are still present.
6. **Given** that confirmation prompt is showing, **When** the user cancels, **Then** nothing is
   deleted and the three remain selected.
7. **Given** a selection has just been deleted, **When** the user looks at the grid, **Then** it
   shows what is actually attached now and nothing is left selected.

---

### User Story 2 - Clear the whole capture in one pass (Priority: P2)

The capture brought in twenty images and none of them belong to this product. The user wants all of
them gone without ticking twenty boxes.

**Why this priority**: It is the worst case of the same pain, and the issue names it explicitly ("a
select-all"). It builds directly on Story 1's selection and delete, so it is a small addition once
Story 1 exists — but Story 1 is useful without it.

**Independent Test**: On a product with several attachments, press select-all, confirm the delete
prompt names every attachment, and observe the grid end up empty.

**Acceptance Scenarios**:

1. **Given** an Attachments grid with several attachments and none selected, **When** the user
   uses select-all, **Then** every attachment in the grid becomes selected.
2. **Given** every attachment is selected via select-all, **When** the user uses select-all again,
   **Then** nothing is selected and the delete-selection action becomes unavailable.
3. **Given** every attachment is selected, **When** the user deletes and confirms, **Then** the grid
   ends up empty and shows the same "nothing attached" message a product with no attachments shows.
4. **Given** the user has ticked some attachments individually, **When** they use select-all,
   **Then** the previously ticked ones stay selected and the rest join them.

---

### User Story 3 - One confirmation on the item photo gallery too (Priority: P3)

A user editing an inventory item ticks several of its photos and presses "Delete Selected". Today
that asks them to confirm the batch, and then asks again for every single photo in it — thirteen
prompts to delete twelve photos. They want the same bargain the Attachments grid now offers: tick,
press, confirm once. They also want a select-all, so clearing a gallery does not mean ticking every
box.

**Why this priority**: The issue asks for this gallery by name alongside the product one. It already
has the checkboxes, so what is missing is a select-all and one confirmation instead of N+1 — a small
correction that leaves the two grids behaving the same way. It is last because the
motivating over-capture lands in the Attachments grid, not here, and this story delivers nothing the
first two depend on.

**Independent Test**: On the Edit Item form for an item with several photos, press select-all, press
"Delete Selected", answer one confirmation naming the count, and observe every photo gone with no
further prompting.

**Acceptance Scenarios**:

1. **Given** an item photo gallery with several photos, **When** the user selects four and presses
   "Delete Selected", **Then** they are asked to confirm exactly once, the prompt names four, and
   confirming removes all four with no further prompts.
2. **Given** that confirmation is showing, **When** the user cancels, **Then** no photo is deleted.
3. **Given** an item photo gallery with several photos, **When** the user uses select-all, **Then**
   every photo in the gallery becomes selected; using it again clears the selection.
4. **Given** the gallery is read-only, **When** the user views it, **Then** neither select-all nor
   "Delete Selected" is offered — as is the case today.
5. **Given** a single photo's own delete control, **When** the user presses it, **Then** it behaves
   exactly as it does today, confirming for that one photo.

---

### Edge Cases

- **A product with no attachments.** The grid shows its empty message; select-all and the
  delete-selection action are either absent or unavailable, and neither can produce a confirmation
  prompt for zero attachments.
- **A product with exactly one attachment.** Selection still works, and the confirmation names one —
  in whatever wording reads correctly for a single file, not "1 attachment(s)".
- **One deletion in the batch fails.** The user is told that it did not fully succeed; the grid is
  refreshed so it shows what is actually attached rather than what the user expected. Attachments
  that were deleted stay deleted — the operation is not rolled back.
- **An attachment in the selection is already gone** (deleted in another tab, or already removed).
  It is treated as successfully removed rather than reported as an error; the end state is what
  matters.
- **Opening an attachment while selecting.** Ticking a tile's selection control must not open the
  image, and opening the image must not change the selection.
- **Selection survives nothing.** After the page reloads for any reason, the selection is empty. No
  selection is remembered across page loads.
- **Deleting the last attachment.** The empty message appears without the user needing to reload.
- **A read-only item photo gallery.** No selection controls, no select-all, no delete — unchanged
  from today.
- **A selected item photo that was never uploaded.** It leaves the gallery like any other member of
  the selection; nothing is asked of the server for it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each attachment in a product's Attachments grid MUST offer a selection control that
  toggles that attachment in and out of the selection.
- **FR-002**: The Attachments grid MUST offer a select-all control that selects every attachment
  currently shown, and, when everything is already selected, clears the selection.
- **FR-003**: The Attachments grid MUST offer a single delete-selection action that is unavailable
  while the selection is empty.
- **FR-004**: The delete-selection action MUST report how many attachments are currently selected.
- **FR-005**: Pressing the delete-selection action MUST ask for confirmation exactly once, and the
  confirmation MUST name the number of attachments that will be deleted.
- **FR-006**: Confirming MUST remove every selected attachment, asking for no further confirmation
  regardless of how many are in the selection.
- **FR-007**: Cancelling the confirmation MUST delete nothing and MUST leave the selection intact.
- **FR-008**: After a deletion attempt — whether it fully succeeded or not — the grid MUST reflect
  what is actually attached to the product, and the selection MUST be empty.
- **FR-009**: If any attachment in the selection could not be deleted, the user MUST be told that the
  deletion did not fully succeed. Attachments that were deleted MUST stay deleted.
- **FR-010**: An attachment that no longer exists MUST count as successfully removed, not as a
  failure.
- **FR-011**: Removing an attachment through a selection MUST have the same effect on stored data as
  removing it through the existing single-attachment delete — including releasing file bytes that
  nothing else references.
- **FR-012**: The existing per-attachment delete control and its behavior MUST remain unchanged.
- **FR-013**: Uploading, viewing and pasting attachments MUST remain unchanged.
- **FR-014**: When the grid becomes empty as a result of a deletion, the empty-grid message MUST be
  shown without requiring a further user action.
- **FR-015**: Deleting a selection in the item photo gallery MUST ask for confirmation exactly once,
  naming the number of photos, and MUST NOT ask again for individual photos in that selection.
- **FR-016**: The item photo gallery MUST offer a select-all control with the same behavior as
  FR-002, and MUST NOT offer it when the gallery is read-only.
- **FR-017**: The item photo gallery's per-photo delete control MUST keep its current behavior,
  including its own confirmation.

### Key Entities

- **Attachment**: a file attached to a product, shown as one tile in the Attachments grid. Already
  exists; this feature adds no fields to it and no new relationships.
- **Selection**: transient, held only while the page is open. Not stored, not shared, not carried
  across page loads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Removing any number of attachments from one product requires exactly one confirmation.
- **SC-002**: Clearing an entire over-captured gallery, whatever its size, takes at most three user
  actions: select-all, delete, confirm.
- **SC-003**: Removing twelve of a product's attachments costs one page reload, against the twelve
  it costs today — and if all twelve are going, three user actions instead of twelve.
- **SC-004**: A user who deletes a selection can tell from the grid alone, without reloading, which
  attachments the product still has.
- **SC-005**: A product's attachments can still be added, viewed and deleted one at a time exactly as
  before, with no change in behavior.
- **SC-006**: Deleting twelve photos from an inventory item costs one confirmation instead of the
  thirteen it costs today.
- **SC-007**: Selecting and bulk-deleting works the same way in both grids — a user who has learned
  one has learned the other.

## Assumptions

- **Two grids, one behavior.** The product Attachments grid is where capture lands and where the
  reported pain occurred, so it gets the feature built (Stories 1–2). The inventory **item photo
  gallery** on the Add/Edit Item forms already has per-photo selection and a bulk delete, so it gets
  the two corrections that bring it in line: a select-all, and one confirmation instead of N+1
  (Story 3).
- **Purchase attachments are out of scope.** They are attached one at a time from the purchases
  table, not by capture, so they do not accumulate the way a captured gallery does.
- **No new deletion semantics.** "Delete" here means exactly what the existing single delete means.
  Nothing becomes recoverable, and nothing that was permanent stops being permanent.
- **No undo.** The confirmation is the safeguard. Note that the existing *single* attachment delete
  asks for no confirmation at all and keeps that behavior under FR-012: one tile is a cheap mistake
  to make and an easy one to notice, a selection is neither.
- **Single user, one page at a time.** There is no second user and no concurrent editor to defend
  against; the issue says so explicitly. Two tabs open on the same product is a curiosity, not a
  case to engineer for beyond FR-010.
- **Selection is not persisted** anywhere — not in the URL, not in storage, not on the server.
- **The confirmation is a plain confirmation**, in keeping with the confirmations the application
  already uses. No new dialog framework.
- **FR-009's "told"** means a visible message on the page, in the same place attachment errors are
  already reported. No new notification mechanism — the item photo gallery keeps reporting its
  outcomes the way it already does.
- **Story 3 changes no other behavior** in the item photo gallery: upload, drag-and-drop, view,
  download and per-photo delete are untouched.
