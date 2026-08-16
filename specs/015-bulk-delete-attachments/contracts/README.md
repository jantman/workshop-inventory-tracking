# Contracts: Delete Several Product Photos at Once

**Feature**: `specs/015-bulk-delete-attachments` | **Date**: 2026-08-16

## No new HTTP surface

This feature adds **no endpoint**, changes **no request or response shape**, and changes **no status
code**. That is the central design decision, argued in `research.md` §1: bulk deletion is the
browser calling the existing single-delete route once per selected attachment.

The contracts below are therefore *consumed*, not *introduced*. They are recorded here because the
feature depends on their exact behavior — particularly the 404 — and a change to any of them would
break it.

## Consumed: `DELETE /api/attachments/<int:attachment_id>`

`app/product/routes.py` → `api_delete_attachment`

| Outcome | Status | Body | How this feature reads it |
|---|---|---|---|
| Attachment removed | `204` | empty | Success. Remove the tile from the selection's tally. |
| No such attachment | `404` | error handler JSON | **Success** (FR-010). It is already gone; that is the requested end state. |
| Anything else / network error | `5xx`, other | — | Failure for that one attachment. Its tile stays; it is counted for the message FR-009 requires. |

Called with the CSRF token via `csrfFetch` (`app/static/js/csrf.js`), same-origin, exactly as the
existing per-tile delete does today.

Side effect, inherited and required by FR-011: `PhotoService.delete_attachment` also deletes the
underlying `Photo` when no `ProductAttachment` or `ItemPhotoAssociation` still references it.
Because two attachments can share a `photo_id`, these calls are issued **sequentially** — see
`research.md` §2.

## Consumed: `DELETE /api/photos/<int:photo_id>`

`app/main/routes.py` — the item photo gallery's delete. Unchanged by this feature, and still called
with a plain `fetch` as it is today; Story 3 changes only how many times it is confirmed, not how it
is called.

## Introduced: DOM contract for the product Attachments card

The card is server-rendered by `app/templates/product/detail.html` and driven by
`app/static/js/product-attachments.js`. The existing hooks — `#attachment-list`, `.attachment-row`,
`#no-attachments`, `.delete-attachment-btn`, `#attachment-alerts` — are load-bearing for
`tests/e2e/test_product_attachments.py` and **must keep their current names and current meaning**.

New hooks, which the E2E tests will bind to:

| Selector | Element | Contract |
|---|---|---|
| `.attachment-select` | one checkbox per tile, inside `.attachment-row` | Carries `data-attachment-id`. Must sit **outside** the `<a>` that opens the full image, so ticking never navigates. |
| `#select-all-attachments` | one checkbox, in a toolbar above the grid | Checked ⇒ every tile checked; unchecking ⇒ none checked. |
| `#delete-selected-attachments` | one button, in the same toolbar | `disabled` while nothing is selected. Its text reports the count. |

The toolbar is rendered only when the product has at least one attachment — a select-all over
nothing is not a control, it is a puzzle.

`#no-attachments` keeps its current behavior: **present only when the product has no attachments**.
`tests/e2e/test_product_attachments.py` asserts `to_have_count(0)` for it while attachments exist,
so it must not become a permanently-present hidden element.

## Introduced: DOM contract for the item photo gallery

Rendered entirely by `app/static/js/photo-manager.js`. Existing hooks `.photo-gallery-grid`,
`.photo-card`, `.photo-select`, `.photo-delete-btn`, `.delete-selected-btn`, `.gallery-actions` and
`.photo-count` keep their names and meaning — `tests/e2e/screenshot_config.yaml` waits on
`.photo-gallery-grid` and `#photo-manager-container`.

| Selector | Element | Contract |
|---|---|---|
| `.select-all-photos` | one checkbox, inside `.gallery-actions` | Same toggle semantics as `#select-all-attachments`. Absent when the gallery is read-only, which it inherits by living inside `.gallery-actions` — that block is already omitted for a read-only gallery. |

## Confirmation text

Not an HTTP contract, but the E2E tests assert on it, so it is fixed here:

- Attachments: `Delete 1 attachment?` / `Delete 7 attachments?`
- Item photos: `Delete 1 photo?` / `Delete 12 photos?`

Singular below two, plural at two and above. `1 attachment(s)` is explicitly ruled out by the spec's
edge cases.
