# Contract: `MoveManager` and its subclasses

`app/static/js/move-manager.js` defines `class MoveManager`. Each page script defines one
subclass and assigns an instance to `window.moveManager` on `DOMContentLoaded`. The e2e
waiter relies on that global.

## Members a subclass supplies

| Member | Item page (`InventoryMoveManager`) | Product page (`ProductMoveManager`) |
|---|---|---|
| `noun` / `nounPlural` | `'item'` / `'items'` | `'product'` / `'products'` |
| `idLabel` | `'JA ID'` | `'Product Code'` |
| `idExample` | `'JA000123'` | `'WIT…'` code |
| `isSubjectId(value)` | `/^JA[0-9]+$/` | `/^WIT[0-9A-HJKMNP-TV-Z]{10}$/` on `value.toUpperCase()` |
| `normalizeId(value)` | identity | `value.toUpperCase()` |
| `isForeignId(value)` | base default `false` | `/^JA[0-9]+$/` |
| `foreignIdMessage(value)` | n/a | names the item Move page |
| `async lookup(id)` | `GET /api/items/{id}` | `GET /api/products/by-code/{id}` |
| `executeUrl` | `/api/inventory/batch-move` | `/api/products/batch-move` |
| `moveRequest(entry)` | `{ja_id, new_location, new_sub_location}` | `{code, new_location, new_sub_location}` |

`lookup(id)` resolves to one of two results:

- `{found: true, location: string|null, subLocation: string|null, label: string}`;
- `{found: false}` on a 404.

It **throws** on a network error or any other non-OK response.

## Base behaviour (unchanged from today's item page except as noted)

- `classifyInput(value)` returns `'id' | 'location' | 'foreign' | 'sub_location'`, tested in
  that order of precedence. The location rule is `^M[0-9]`, `^T-?[0-9]`, or exactly `Other`.
- The state names are `id`, `location`, `id_or_sub_location` and `bulk_location`. The state
  is held in `currentExpectedInput`, alongside `currentId`, `currentLocation`, `moveQueue`,
  `pendingMoves` and `bulkGroupIds`.
- Badge wording is built from `idLabel`:
  - `Waiting for Location`
  - `Waiting for ${idLabel} or Sub-Location`
  - `Ready for ${idLabel}`
  - `Waiting for Destination`
  - `Done - Ready to Validate`

  On the item page these are the same strings as today.
- Validation calls `lookup` once per entry:
  - found → `validated`, which also refreshes current location, sub-location and label;
  - `{found:false}` → `not_found`;
  - thrown → `error`.
- Queue rendering:
  - `currentLocation === null` renders as muted "None", and "Unknown" only appears when
    lookup failed;
  - the "Cleared" marker is unchanged.
- `#status-text` reads `All data cleared…` after a successful execute. `waits.wait_for_move_executed`
  depends on that wording.

## Test hook

`tests/e2e/waits.py::scan_on_move_page` reads the following through `page.evaluate` before
typing:

- `window.moveManager.classifyInput(value)`
- `currentExpectedInput`
- `moveQueue.length`
- `pendingMoves.length`
- `bulkGroupIds.length`
- `currentId !== null`
- `idLabel`

It no longer keeps a Python copy of the patterns.
