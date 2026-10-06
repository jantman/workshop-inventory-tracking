# Data Model: Move Products Between Locations by Scanning

No schema change. Existing columns written:

| Table | Column | Type | Notes |
|---|---|---|---|
| `products` | `location` | String(100), nullable | Set to the queued location, stripped |
| `products` | `sub_location` | String(100), nullable | Set to the queued sub-location, stripped; `NULL` when none queued or blank |
| `products` | `last_modified` | DateTime (onupdate) | Bumped by the update, as with any edit |

Nothing else on the product changes (FR-010). There is no history or audit row, matching the
edit form.

## Queue entry (browser only)

Built by `MoveManager`, never persisted.

| Field | Meaning |
|---|---|
| `id` | JA ID or `WIT` code (normalized) |
| `newLocation` | Destination location as scanned |
| `newSubLocation` | Destination sub-location, or `null` (clears on execute) |
| `currentLocation` | From `lookup()` at queue time; `null` = none set; `'Unknown'` = lookup failed |
| `currentSubLocation` | From `lookup()`; `null` = none |
| `itemInfo` | Display label from `lookup()` (item display name / product description) |
| `status` | `pending` → `validated` \| `not_found` \| `error` |
| `error` | Reason, when not validated |

## Scan state machine (shared)

States: `id`, `location`, `id_or_sub_location`, `bulk_location`. These match the item
page's existing machine, renamed per research R3.

| From | Input class | To | Effect |
|---|---|---|---|
| `id` | id | `location` | `currentId` set |
| `id` | location / sub_location / foreign | `id` | refused (alert) |
| `location` | location | `id_or_sub_location` | `currentLocation` set |
| `location` | id | `location` | previous abandoned with warning (#107) |
| `location` | sub_location / foreign | `location` | refused |
| `id_or_sub_location` | id | `location` | previous finalized without sub-location |
| `id_or_sub_location` | sub_location | `id` | finalized with sub-location (or applied to group) |
| `id_or_sub_location` | location / foreign | same | refused |
| `bulk_location` | location | `id_or_sub_location` | whole preselected group queued |
| `bulk_location` | anything else | same | refused |

A `foreign` input only ever arises on the product page, where it is a `JA` label.
