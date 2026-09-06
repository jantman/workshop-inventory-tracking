# Phase 1 Data Model: An Explicit "I Counted the Shelf" at Receipt

**Feature**: `specs/041-counted-at-receipt` | **Date**: 2026-09-06

**No schema change. No Alembic revision. No new entity, column, index or constraint.**

This document exists to say precisely that, and to record what the one existing field means
after this feature — because the change here is entirely to *who is allowed to write* a field
that already exists.

## The field this feature is about

### `products.quantity_updated_at`

| | |
|---|---|
| **Type** | `DATETIME`, nullable — unchanged |
| **Defined at** | `app/database.py:854` |
| **Read by** | `Product.quantity_age` (`app/database.py:951`), which subtracts it from `utc_now()`; rendered on the product detail page and the reorder list |
| **Basis** | `utc_now()` — a recorded instant, never `local_now()` and never a date the operator typed (see `app/utils/clock.py`, and feature 037) |

**Meaning: unchanged.** It is the last time an operator actually looked at the stock. Feature 008
established that and this feature does not touch it. What changes is only the list of acts that
qualify as looking.

**Writers, before this feature:**

| Writer | Writes | Why it qualifies |
|---|---|---|
| `CatalogService.create_product` (`:224`) | `utc_now()` when a count is given at creation | The operator supplied a number |
| `CatalogService.set_quantity` (`:446`) | `utc_now()` when a count is set or changed | The operator typed a number, or pressed `+`/`−` at the shelf |
| `CatalogService.set_quantity` (`:441`) | `None` when tracking is switched off | An age for a count that no longer exists is worse than no age |

**Writers, after this feature:** the three above, plus one:

| Writer | Writes | Why it qualifies |
|---|---|---|
| `CatalogService.receive_purchase` | `utc_now()` when `counted=True` **and** `product.quantity is not None` | The operator explicitly asserted that they counted what is on the shelf |

The invariant that survives all four: **every writer is an operator act.** Nothing writes this
field on the operator's behalf, and receiving with the assertion unmade still writes nothing —
which is the whole of feature 008's FR-008, now with its one named exception.

## The field this feature deliberately does not add

There is **no** per-purchase record of whether a receipt carried the assertion. No
`purchases.counted` column, no audit row, no flag on the receipt.

The evidence the operator produced is the count's age; a second stored fact about how that age
came to be would be a fact nothing displays, that every future write path would have to
maintain, and that would invite exactly the "two competing dates for one assertion" that feature
008's FR-015 and SC-007 forbid.

## Entities

| Entity | Change |
|---|---|
| `Product` (`app/database.py:821`) | None to its shape. `quantity`, `quantity_updated_at`, `reorder_threshold`, `stock_status`, `stock_status_updated_at` all keep their types, nullability and meanings. `Product.to_dict` is unchanged. Only the docstring on `quantity_age` changes, and only because it currently forbids what this feature adds. |
| `Purchase` (`app/database.py:1030`) | None. `received_date`, `quantity`, `unit_price`, `notes` are untouched, and `Purchase.to_dict` is unchanged. |

## State transitions

The tri-state count is unchanged and this feature reaches none of its transitions:

```
not tracked (quantity IS NULL)  ──set_quantity(n)──▶  tracked (quantity = n, age = now)
        ▲                                                     │
        └──────────────set_quantity(None)─────────────────────┘
                       (age cleared)
```

`receive_purchase` sits entirely inside the *tracked* state and moves nothing between states,
with or without the assertion:

| Starting state | `counted=False` | `counted=True` |
|---|---|---|
| Not tracked | count and age both stay `NULL` | count and age both stay `NULL` — receiving never begins tracking (spec FR-006) |
| Tracked, receipt has a quantity | count `+= received`; age unchanged | count `+= received`; age `= utc_now()` |
| Tracked, receipt has no quantity | nothing changes | age `= utc_now()`; count unchanged (spec Story 1 scenario 5) |
| Tracked, already received | count and age unchanged | age `= utc_now()`; count unchanged (spec FR-010) |

## Validation rules

The one new input is a boolean, and it comes from an HTML checkbox: present means asserted,
absent means not. There is nothing to reject — an unrecognised value is simply not `'on'`, which
is the safe default and the one that preserves feature 008's rule. No new exception type, and no
new use of `ValidationError`.

The existing validation order is load-bearing and unchanged: `receive_purchase` validates
quantity, price and description **before** opening its session, so a refusal writes nothing at
all — including no count age (spec FR-009).
