# Data Model: Fix the item hand-off into Move and Shorten

**Feature**: `specs/026-fix-bulk-move-handoff` | **Date**: 2026-08-24

**No persisted schema changes.** No table, column, or index is added or altered, and no Alembic
revision ships with this feature. Everything below is client-side page state, plus one
server-rendered value passed into a template. The persisted `InventoryItem` and its history
invariants are untouched — preselected items execute through the existing batch-move path.

---

## 1. Hand-off payload (transient, in the request)

Produced by a list page, consumed by a receiving page. Not stored anywhere.

| Field | Type | Notes |
|---|---|---|
| `ja_id` | string | Comma-separated JA IDs. A single item is a list of one. Absent means a normal, non-hand-off arrival. |

**Rules**

- Each element must match `JA[0-9]+` (the existing `isJaId` pattern) to be considered.
- Order is preserved as given, so the queue reads in the order the user saw on the list.
- Duplicates collapse to the first occurrence (FR-006).
- Empty or absent → the receiving page behaves exactly as today (FR-004).
- Whitespace around elements is trimmed; empty elements are discarded.

## 2. Resolved hand-off (server-rendered into the page)

What the route hands the template after checking each identifier against storage.

| Field | Type | Notes |
|---|---|---|
| `preselected_items` | list | The items that can be acted on, in payload order |
| `rejected_items` | list of `{ja_id, reason}` | Named on screen, never silently dropped (FR-005) |

**Rejection reasons** — `not_found` (no such JA ID) and `inactive` (exists but is not the active
row). Both are reported to the user by JA ID. Rejecting inactive rows is what keeps Principle VI
intact: a hand-off must not queue a historical row for a move.

**States**: if `preselected_items` is empty *and* `rejected_items` is not, the page says so
plainly rather than looking like a normal empty arrival (spec, Edge Cases).

## 3. Pending move (client-side, new)

The state this feature introduces: a preselected item on the Move page that has arrived but has
no destination yet. It exists only between page load and the group being queued.

| Field | Type | Notes |
|---|---|---|
| `jaId` | string | |
| `currentLocation` | string | For display; `Unknown` if it cannot be determined |
| `currentSubLocation` | string \| null | |

A pending move is **not** a queued move and is never validated, executed, or counted in the
queue badge. It has no destination, so there is nothing to validate; giving it one is the entire
transition below.

## 4. Queued move (client-side, unchanged)

The existing `moveQueue` entry — `jaId`, `newLocation`, `newSubLocation`, `currentLocation`,
`currentSubLocation`, `status`, `timestamp`. **This feature does not change its shape.** A
preselected item becomes an ordinary queued move, indistinguishable from a scanned one, which is
why validation and execution need no changes (FR-013).

---

## 5. Move page state machine

Existing states are `ja_id`, `location`, `ja_id_or_sub_location`. One state is added.

```
                    ┌─ page loaded WITH preselected items
                    ▼
             ┌──────────────┐   location   ┌──────────────────────┐
             │ bulk_location│─────────────▶│ ja_id_or_sub_location│
             └──────────────┘   (NEW)      └──────────────────────┘
              queues all N as                    │        │
              ordinary queued moves     sub-loc ─┘        └─ JA ID / >>DONE<<
                                        applies to             │
                                        whole group            ▼
   ┌─ page loaded WITHOUT preselected items ──────────▶ ┌────────┐
                                                        │ ja_id  │◀── resting state
                                                        └────────┘
                                                             │ JA ID
                                                             ▼
                                                        ┌──────────┐
                                                        │ location │
                                                        └──────────┘
```

**Transitions added**

| From | Input | To | Effect |
|---|---|---|---|
| `bulk_location` | valid location | `ja_id_or_sub_location` | Every pending move becomes a queued move with that destination (FR-008) |
| `bulk_location` | anything else | `bulk_location` | Rejected with an explanation (FR-012) |
| `bulk_location` | `>>DONE<<` | `bulk_location` | Nothing queued; the page says why (spec, Edge Cases) |

A sub-location supplied from `ja_id_or_sub_location` after a group was queued applies to **all**
items of that group (FR-009), not just the last one — this is the one place the existing
sub-location handling needs to know a group happened.

Once the group is queued the machine reaches `ja_id` by the existing route and hand scanning
continues normally into the same batch (FR-011).

**Transitions changed for issue #107** — see [research.md](./research.md) R3 for why the trigger
is unestablished and the fix targets the class:

| From | Input | Today | Required |
|---|---|---|---|
| `location` | JA ID | Warns, clears the field, **state unchanged** — the wedge | Must resolve rather than bounce; a JA ID here unambiguously means the previous item's location was missed |

**Invariant**: no input may leave the machine in a state from which no valid input can make
progress. That property is what the wedge violates, and it is what the #107 tests assert.

## 6. Shorten page

The handed-off item populates the existing `source_ja_id` field (`#source-ja-id` in
`shorten.html`). No new state, and the page's own workflow is unchanged — this is a prefill, not
a mode.
