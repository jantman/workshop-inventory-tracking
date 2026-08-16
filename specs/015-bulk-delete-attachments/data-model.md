# Data Model: Delete Several Product Photos at Once

**Feature**: `specs/015-bulk-delete-attachments` | **Date**: 2026-08-16

## Schema changes

**None.** No table, column, index or constraint changes, and therefore **no Alembic revision**.

This is worth stating explicitly because the constitution requires every schema change to ship as a
reversible Alembic revision (Principle V). A feature that adds a migration directory entry here would
be a sign that something has gone wrong with the plan.

## Entities touched (existing, unchanged)

### `ProductAttachment` (`app/database.py`, table `product_attachments`)

One file attached to a product **or** a purchase, never both — a database check constraint says so.
Relevant fields for this feature:

| Field | Role here |
|---|---|
| `id` | Identifies the attachment in `DELETE /api/attachments/<id>`; rendered as `data-attachment-id` on each tile's delete control today, and now also on its selection control. |
| `product_id` | Scopes the grid. The Attachments card renders the attachments of one product. |
| `photo_id` | The bytes. Shared: two attachments can point at the same photo. |
| `display_order` | The grid's order. Untouched — deletion does not renumber. |

Read only; no field gains a meaning, and none is written by this feature except by being deleted.

### `Photo`

The stored bytes. Deleted by `PhotoService.delete_attachment` when the last reference to it goes
away — the existing reference check counts both `ProductAttachment` and `ItemPhotoAssociation` rows.
This feature reaches that logic through the same route it always used, so the reference-counting
behavior is inherited rather than reimplemented (FR-011).

The shared-`photo_id` case is why deletes are issued **one at a time**; see `research.md` §2.

## Client-side state (new, transient)

Nothing here is persisted, serialized, sent to the server, or survives a page load.

### Product Attachments grid — selection

| State | Where it lives | Notes |
|---|---|---|
| Whether an attachment is selected | The `checked` property of its tile checkbox, in the DOM | The DOM is the state. No parallel JavaScript array to keep in sync with it. |
| The selection | Derived — the checked boxes, read at the moment it is needed | Never cached. |
| Select-all's own state | Its `checked` property | Toggles: not-all-selected → select all; all-selected → clear. |
| "Delete Selected (N)" enabled / label | Derived from the count of checked boxes on every `change` | Disabled at N = 0 (FR-003). |

Deriving the selection from the DOM rather than tracking it alongside is deliberate: the tiles are
server-rendered, there is no client-side model of them to attach a flag to, and inventing one would
be a second source of truth for a checkbox.

### Item photo gallery — selection

Already exists and is **not** restructured: `photo.selected` on each entry of the manager's
`photos` array, set by the tile checkbox's `change` handler. This feature adds a select-all that
writes to those same flags and checkboxes, and reads them once in `deleteSelectedPhotos`.

The two grids therefore hold selection differently — DOM in one, an object flag in the other —
because each follows what its own grid already does. Unifying them would mean rewriting one of the
two galleries to no user-visible benefit.

## State transitions

The only transition this feature introduces is on an attachment, and it is the one that already
existed:

```
attached ──(delete, individually or as part of a selection)──> gone
```

There is no "marked for deletion" state, no soft delete, no recycle bin, and no undo. A selected
attachment is not in a different state from an unselected one — the selection lives in the browser,
not in the data.
