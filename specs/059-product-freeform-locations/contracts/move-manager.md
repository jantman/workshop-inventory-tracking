# Contract delta: `MoveManager` (amends specs/057-product-location-move/contracts/move-manager.md)

| Member | Item page (`InventoryMoveManager`) | Product page (`ProductMoveManager`) |
|---|---|---|
| `isLocation(value)` | base: `^M[0-9]`, `^T-?[0-9]`, or exactly `Other` | base rule, **or** any non-empty value while `currentExpectedInput` is `location` or `bulk_location` |
| `locationHint` | base: `' (M*, T*, or Other)'` | `''` |

- `classifyInput(value)` is therefore state-dependent on the product page. The e2e waiter
  already evaluates it in the page's current state before typing, so the test hook needs no change.
- `move_page(...)` macro gains `location_example`: the item page passes `M1-A, T-5, or Other`
  (its text is unchanged) and the product page passes a free-text example.
