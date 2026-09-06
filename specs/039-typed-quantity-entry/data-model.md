# Data Model: Type a tracked count instead of clicking to it

**Feature**: 039-typed-quantity-entry | **Date**: 2026-09-06

## Schema changes

**None.** No table, column, index, or constraint changes, and therefore **no Alembic revision**.
This feature adds a way to reach states the schema already stores.

## Entities touched (all read or written through existing paths)

### Product — the on-hand count

`app/database.py`, table `products`. Unchanged.

| Field | Type | Meaning here |
|---|---|---|
| `quantity` | `Integer`, nullable | The tri-state. A number is a count, `0` is "tracked, none on hand", `NULL` is "not counted". |
| `quantity_updated_at` | `DateTime`, nullable | When the count was last established. Set whenever `quantity` is set; cleared when tracking stops. |
| `reorder_threshold` | `Integer`, nullable | Untouched by this feature. Already cleared when tracking stops. |
| `stock_status` | `String`, nullable | The manual low/out flag. Untouched by this feature. |

**Invariant preserved**: `quantity_updated_at` is non-`NULL` exactly when `quantity` is non-`NULL`.
Enforced today by `CatalogService.set_quantity()`, which this feature calls rather than bypasses.

**State transitions this feature adds a route to** (it adds no new states):

| From | Action | To |
|---|---|---|
| not counted (`NULL`) | start counting, entry empty | `0`, dated now — *unchanged from today* |
| not counted (`NULL`) | start counting, entry `n` | `n`, dated now — **new route** |
| counted (`m`) | set, entry `n` | `n`, dated now — **new route** |
| counted (`m`) | set, entry `m` (unchanged) | `m`, **re-dated** now — new route, and deliberate: FR-003 |
| counted (`m`) | set, entry empty | refused; `m` unchanged, not re-dated |
| counted (`m`) | set, entry invalid | refused; `m` unchanged, not re-dated |
| counted (`m`) | + / − | `m ± 1`, floored at 0 — *unchanged from today* |
| counted (`m`) | stop counting | `NULL`, date cleared, threshold cleared — *unchanged from today* |

### Purchase — the received total

`app/database.py`, table `purchases`. Read only; nothing written.

| Field | Type | Use here |
|---|---|---|
| `quantity` | `Integer`, nullable, `> 0` when present | Summed. A `NULL` contributes nothing. |
| `received_date` | `DateTime`, nullable | Selects the rows. `Purchase.is_outstanding` is `received_date is None`, so *received* is its negation. |
| `product_id` | FK → `products.id` | Scopes the sum to one product. |

## Derived value

### `received_total`

A new entry in the `product/detail.html` template context, computed in `product_detail`
(`app/product/routes.py`) from the purchase list the route has already fetched:

```
received_total = sum of purchase.quantity
                 over purchases where not purchase.is_outstanding
                 and purchase.quantity
```

| Property | Value |
|---|---|
| Type | `int` |
| Range | `0` or greater |
| Persisted | No. Computed per render. |
| Rendered when | `product.quantity is none` **and** `received_total > 0` |
| Rendered never when | the product is being counted (any `quantity is not none`) — FR-013 |

`0` and "no received purchases" are the same case and produce the same result: nothing is
rendered. There is no need to distinguish them, and no `None` sentinel.

## Validation

All of it already exists and is unchanged. `CatalogService._validate_quantity()` accepts `None`
and any whole number `>= 0`, and raises `ValidationError` otherwise. The API turns that into a
`400` with the message.

The one rule this feature adds is a client-side one, because it cannot be expressed at the
service layer without changing what an empty value means for product creation (see
`research.md` §2):

- An **empty** entry committed by the *Set* control is refused in the browser and never sent.
  The service would read `''` as `None`, which means "stop counting" and is not what an empty box
  is saying.

## What is not modelled

- No history of count changes. `quantity_updated_at` remains a single "last established" stamp,
  as it is today. An audit trail of counts is out of scope.
- No stored suggestion, no "suggested count" column, no dismissal state for the received-total
  line. It is derived at render time and has no memory.
