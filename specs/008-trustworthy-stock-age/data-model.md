# Phase 1 Data Model: Trustworthy Stock Age

## One column

```
products.stock_status_updated_at   DATETIME  NULL
```

When the operator's manual flag was last set. `NULL` means one of two things, and the template already distinguishes them because it only renders the age inside a `{% if product.stock_status %}` guard:

| `stock_status` | `stock_status_updated_at` | Means | Shown as |
|---|---|---|---|
| `NULL` | `NULL` | No flag | nothing |
| `'low'` / `'out'` | a date | Flagged, and this is when | *Flagged low 3 months ago* |
| `'low'` / `'out'` | `NULL` | Flagged before this feature shipped | *Flagged low at an unknown time* |
| `NULL` | a date | **Cannot occur.** `set_stock_status` and `receive_purchase` clear both together | — |

This is deliberately the same shape as `quantity` / `quantity_updated_at`, including the part where the fourth row is prevented in code rather than by a constraint. `research.md` records why no CHECK constraint was added.

### Revision `b1a0c0d10010` — add the flag's date

`down_revision = 'b1a0c0d10009'`, the current head.

- **upgrade**: `op.add_column('products', sa.Column('stock_status_updated_at', sa.DateTime(), nullable=True))`. Nullable, no server default, **no backfill** — FR-005 and SC-006 require an unrecorded age to stay unrecorded, and `research.md` says why `last_modified` is not a substitute.
- **downgrade**: `op.drop_column('products', 'stock_status_updated_at')`.

### Reversibility

The downgrade loses every flag date and nothing else. Flags themselves, counts, count ages and purchases are untouched, so downgrading returns the catalogue to exactly today's behaviour: flags with no age. That is the whole of the data loss and it is inherent to reversing an added column; there is no guard worth writing for it, unlike `b1a0c0d10009`'s narrowing, where reversing could have truncated text.

Exercise the pair against a disposable MariaDB container, never against the database named in `.env` — neither test suite runs migrations, so `upgrade` and `downgrade` are otherwise unexercised code.

## Two properties on `Product`

### `stock_status_age -> Optional[timedelta]`

```python
@property
def stock_status_age(self) -> Optional[timedelta]:
    """How long ago the manual flag was set (008 FR-001, FR-004).

    None when there is no flag, and also when there is one but no date was
    recorded -- an unknown age is not an error, and the display renders it as
    unknown rather than raising.
    """
    if self.stock_status is None or self.stock_status_updated_at is None:
        return None
    return datetime.now() - self.stock_status_updated_at
```

Deliberately a line-for-line mirror of the existing `quantity_age`, down to the double `None` guard and the reason for it. Two properties that answer the same question about different evidence should not be two different shapes.

### `quantity_age` — unchanged

Its meaning changes without its code changing. Before this feature it answered "when was this number last written?"; after it, it answers "when did somebody last count?", because the one writer that was not a person has stopped writing. That is the point of the feature, and it is worth saying in the docstring so the next reader does not restore the deleted line as a bug fix.

## Field addition to `Product.to_dict()`

`'stock_status_updated_at': self.stock_status_updated_at.isoformat() if self.stock_status_updated_at else None`, placed next to `stock_status`, matching the `quantity_updated_at` line four rows above it. Additive; see `contracts/product-json.md`.

## Service rules

Stated as behaviour; signatures are in `contracts/catalog-service.md`.

**`set_stock_status(product_id, stock_status)`**

- Setting to `'low'` or `'out'` writes the value *and* `stock_status_updated_at = datetime.now()` — including when the value equals what is already stored (FR-002). The timestamp write is what makes a re-assertion produce an `UPDATE` at all; see `research.md`.
- Clearing writes `NULL` to both (FR-003).

**`receive_purchase(...)`**

- The line `product.quantity_updated_at = datetime.now()` is **deleted** (FR-008). The increment on the line above it stays (FR-007).
- Where the flag is cleared, `stock_status_updated_at` is cleared with it (FR-006).
- Both are already inside the `if not already_received` guard, so receiving twice remains a no-op for stock.

**`set_quantity`, `create_product`** — unchanged. They are the operator entering a count, which is what FR-010 says should stamp the age.

## What is not modelled

- **No history table.** One operator, one current fact. A flag transition log is a schema, a relationship, a cascade and a query in exchange for a date.
- **No second timestamp on the count** (FR-015). A change the operator did not make is evidenced by the purchase that made it.
- **No `stock_status_age` on the reorder query.** `get_reorder_products` returns the `Product` itself inside each entry, so the template reaches the property directly. Nothing is added to the entry dict.
- **No index.** Nothing filters or sorts on the new column (FR-013, FR-014), and adding one for a column only ever read through an already-loaded row would be indexing beyond the obvious.
