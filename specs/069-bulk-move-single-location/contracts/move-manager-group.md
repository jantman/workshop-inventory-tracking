# Contract: scanned group on the move pages

Extends `specs/057-product-location-move/contracts/move-manager.md` (frozen; not edited).

## State

- New `currentExpectedInput` value `group_location`: two or more scanned IDs waiting for one
  destination, held in `pendingMoves`.
- `#scanner-status` in `group_location`: `Waiting for Destination` (same wording as
  `bulk_location`).
- `#status-text`: `N <nouns> awaiting a destination. Scan the next <idLabel>, or the
  location all N are going to.`

## Markup (desktop macro and handheld template)

```
#scan-group                      card; class d-none when the group is empty
  #scan-group-count              "N <noun|nouns> awaiting a destination"
  #scan-group-rows               tbody; one tr[data-id] per pending entry, in scan order
    td  ID + .pending-label
    td.pending-current-location
    td.pending-current-sub-location
    td  button.scan-group-remove[data-id]
```

Rows are appended synchronously when the ID is accepted; current-location cells fill in when
the lookup returns. `renderPendingMove()` fills rows in either `#pending-moves` or
`#scan-group-rows`.

## Test hook

`scan_on_move_page` additionally treats a scanned ID as a duplicate when it is in
`pendingMoves` or equals `currentId`, and adds these transitions:

| Pre-state | Input | Wait |
|---|---|---|
| `location` | new ID | `#scan-group-rows tr` count = 2 |
| `group_location` | new ID | `#scan-group-rows tr` count = pending + 1 |
| `group_location` | location | `#queue-count` = queued + pending |
| `group_location` | sub-location / `>>DONE<<` / duplicate | alert count + 1 |
