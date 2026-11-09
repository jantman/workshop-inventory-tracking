# Data Model: Bulk Move to a Single Location by Scanning

No persistent data changes. Page-side state only.

## Pending entry (`MoveManager.pendingMoves[]`)

| Field | Meaning |
|---|---|
| `id` | Normalized subject ID (JA ID or product code) |
| `currentLocation` / `currentSubLocation` | From `lookup()`; `'Unknown'` until it returns or if it fails, `null` when not set |
| `itemInfo` | Label from `lookup()` |
| `ready` | Promise resolving once the lookup has filled the fields above (new) |

Used by both the handed-over group (`bulk_location`) and the scanned group (`group_location`).

## State machine (`currentExpectedInput`)

| From | Input | To | Effect |
|---|---|---|---|
| `id` | ID | `location` | `currentId = id` (unchanged) |
| `location` | ID (new, ≠ `currentId`) | `group_location` | `pendingMoves = [currentId, id]`, `currentId = null`, two rows rendered |
| `location` | ID = `currentId` | `location` | refused: already waiting |
| `location` | location | `id_or_sub_location` | unchanged |
| `group_location` | ID (new) | `group_location` | appended to `pendingMoves`, row rendered |
| `group_location` | ID (waiting/queued/in flight) | `group_location` | refused with message |
| `group_location` | location | `id_or_sub_location` | whole group queued; `bulkGroupIds` = group; `currentId = null` |
| `group_location` | sub-location | `group_location` | refused (items page; on products this is a location) |
| `group_location` | `>>DONE<<` | `group_location` | refused: N still need a destination |
| `group_location` | Remove last row | `id` | group gone |
| `id_or_sub_location` (after group) | sub-location | `id` | applied to the group (unchanged 026 behaviour) |
| `id_or_sub_location` (after group) | ID | `location` | new move (unchanged) |
| `bulk_location` | anything | — | unchanged (026) |
| any | Clear All | `id` | group discarded |
