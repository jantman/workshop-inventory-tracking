# Contract: The item hand-off

**Feature**: `specs/026-fix-bulk-move-handoff` | **Date**: 2026-08-24

The interface this feature defines is between the app's own pages: a list page names items, a
working page acts on them. It had no contract before, which is why two producers disagreed and
neither receiver read anything. This document is that contract.

---

## 1. The convention

```
GET /inventory/move?ja_id=JA000101,JA000102,JA000117
GET /inventory/shorten?ja_id=JA000101
```

**One parameter, `ja_id`, comma-separated. A single item is a list of one.** No other spelling is
accepted; `items=` is retired. Rationale and the alternatives rejected are in
[research.md](../research.md) R1.

**Producers** — all four must emit exactly this form:

| Control | Source | Change |
|---|---|---|
| Inventory list → Bulk Move Selected | `inventory-list.js` `bulkMoveSelected()` | `items` → `ja_id` |
| Search → Bulk Move Selected | `inventory-search.js` `handleBulkMove()` | already `ja_id`; unchanged |
| Row → Move | `item-actions.js` `showMoveDialog()`, `inventory-table.js` row dropdown | already `ja_id`; unchanged |
| Row → Shorten | `item-actions.js` `showShortenDialog()`, `inventory-table.js` row dropdown | already `ja_id`; unchanged |

**Consumers** — `inventory_move()` and `inventory_shorten()` in `app/main/routes.py`.

## 2. Parsing rules

Applied identically by both consumers:

1. Absent or empty → no hand-off; render exactly as today.
2. Split on `,`; trim each element; discard empties.
3. Keep only elements matching `JA[0-9]+`; anything else is rejected as `not_found`.
4. Collapse duplicates to first occurrence, preserving order.
5. Resolve each against storage: the active row → accepted; no such ID → `not_found`; exists but
   not active → `inactive`.
6. Shorten takes the first accepted item; a longer list there is not an error, since the page
   handles one item and the row action only ever sends one.

Validation here serves correctness, not defense (constitution, Operating Context): a malformed
identifier is rejected because it cannot name an item, not because it might be hostile. No
sanitization layer.

## 3. What the receiving page must render

| Condition | Move page | Shorten page |
|---|---|---|
| No hand-off | Today's behavior, unchanged | Today's behavior, unchanged |
| All accepted | Items listed as awaiting a destination; prompt states the count and that the next input is the destination for all of them | `source_ja_id` prefilled |
| Some rejected | Accepted items proceed; rejected ones named on screen with their reason | Prefill the first accepted; name the rejected |
| All rejected | Say so plainly — must not be indistinguishable from a normal empty arrival | Say so plainly; field left empty |

Rejected items are **never** silently dropped (FR-005). A hand-off that quietly loses an item is
the bug this feature exists to fix, in miniature.

## 4. Response semantics

Both routes stay `GET`-addressable and side-effect free. Rendering a hand-off changes nothing in
storage; the move is committed only by the existing batch-move execution path, and the shorten by
the existing form POST. A hand-off URL is safe to reload, bookmark, or share on the LAN.

Both routes remain thin (Principle II): read the parameter, resolve identifiers through the
existing storage interface, hand a list to the template. No ORM query or raw SQL in a route.

## 5. Downstream: unchanged interfaces

Stated so the implementation does not drift into them.

- **`GET /api/items/{ja_id}`** — still how the Move page learns an item's current location. Reused
  for preselected items; not modified, not batched. Batching would be an optimization without a
  measurement (Principle I).
- **The batch-move execution endpoint** — unchanged. Preselected items reach it as ordinary queued
  moves, which is what keeps the item-history invariants intact by reuse rather than by new code.
- **The shorten POST** — unchanged. This feature prefills a field; it does not alter submission.
- **No new endpoint is added by this feature.**

## 6. Conformance

The contract is held by tests that operate the real controls (FR-019). A test that builds one of
these URLs by hand and calls `page.goto` does **not** conform: it verifies a receiver against a
URL the test author wrote rather than one the application produces, which is precisely how the
`items=` / `ja_id=` split survived. See [research.md](../research.md) R4.
