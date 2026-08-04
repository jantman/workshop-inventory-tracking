# Phase 1 Data Model: Product Catalog & Purchase Tracking

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

All tables are new. **No existing table is modified**, and in particular `inventory_items` and its
JA-ID history invariants are untouched (Constitution VI). The one existing table this feature
*reuses* is `photos`, via a new association table (§6).

Layer placement follows Constitution II: enums and dataclasses in `app/models.py`, SQLAlchemy
models in `app/database.py`, all logic in `app/catalog_service.py`, nothing in routes.

---

## 1. `products`

The distinct kind of thing the workshop holds. Its identity is its own row — **never** a vendor's
item identifier (FR-008).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Integer` PK autoincrement | no | Surrogate identity. FR-008 depends on this being independent of every external code. |
| `description` | `String(255)` | no | The operator's authoritative human-readable identity (FR-003). Printed on the label. |
| `manufacturer` | `String(200)` | yes | |
| `manufacturer_part_number` | `String(100)` | yes | Convenience copy; the authoritative form is a `product_identifiers` row of type `MPN`. |
| `specifications` | `Text` | yes | Free-form, operator-authored. Never machine-generated (spec constraint). |
| `category_path` | `String(512)` | yes | Materialized path, canonical form per research §6. Indexed. `NULL` = uncategorized. |
| `location` | `String(100)` | yes | Optional storage location (FR-033). |
| `quantity` | `Integer` | yes | **Tri-state** (FR-022/023): `NULL` = not tracked, `0` = none on hand, `>0` = count. Default `NULL`. |
| `quantity_updated_at` | `DateTime` | yes | When `quantity` was last set. Drives the age display (FR-024). |
| `reorder_threshold` | `Integer` | yes | Only meaningful when `quantity` is not `NULL` (FR-026). |
| `stock_status` | `String(20)` | yes | Manual flag (FR-025): `NULL`, `'low'`, or `'out'`. Independent of `quantity`. |
| `notes` | `Text` | yes | |
| `date_added` | `DateTime` | no | `default=func.now()` |
| `last_modified` | `DateTime` | no | `default=func.now(), onupdate=func.now()` |

**Constraints**

- `CheckConstraint('quantity IS NULL OR quantity >= 0')` — a count is never negative.
- `CheckConstraint('reorder_threshold IS NULL OR reorder_threshold >= 0')`
- `CheckConstraint("stock_status IS NULL OR stock_status IN ('low','out')")`
- Index on `category_path` (prefix filtering, research §6).
- Index on `description` for search (FR-032).

**Validation (service layer, raised as `ValidationError` before any write)**

- `description` non-empty after strip, ≤255 chars.
- `category_path` normalized through `app/utils/category.py`; over-length after normalization is
  a rejection, not a truncation.
- Setting `quantity` from `NULL` to a value, or to a different value, sets `quantity_updated_at`.
  Setting it *back* to `NULL` (stop tracking) clears `quantity_updated_at`.
- `reorder_threshold` may only be set when `quantity` is not `NULL`.

---

## 2. `purchases`

One acquisition of one product. A product has many; ordering is chronological by `order_date`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Integer` PK autoincrement | no | |
| `product_id` | `Integer` FK → `products.id` `ON DELETE CASCADE` | no | Indexed. |
| `vendor` | `String(200)` | no | FR-004. |
| `vendor_item_id` | `String(100)` | yes | The vendor's own identifier (ASIN, part no.). **Not** identity — see FR-008. Indexed. |
| `listing_title` | `String(500)` | yes | Captured at order time (FR-020); the raw vendor title, distinct from `products.description`. |
| `order_date` | `DateTime` | yes | |
| `received_date` | `DateTime` | yes | `NULL` = outstanding (FR-005). Indexed — the reorder view filters on it. |
| `quantity` | `Integer` | yes | As ordered / as received (FR-004). |
| `unit_price` | `Numeric(10, 2)` | yes | **`Decimal`, never `float`** (Constitution III). |
| `order_reference` | `String(200)` | yes | Order number; also filled from ECIA `K` / `1K`. |
| `notes` | `Text` | yes | |
| `date_added` | `DateTime` | no | |
| `last_modified` | `DateTime` | no | |

**Constraints**

- `CheckConstraint('quantity IS NULL OR quantity > 0')`
- `CheckConstraint('unit_price IS NULL OR unit_price >= 0')`
- Index on `(product_id, order_date)` — the purchase-history read (FR-006).
- Index on `received_date` — the outstanding-order derivation (FR-028).

**Validation**

- `received_date` must not precede `order_date` when both are set.
- Marking received when already received is a no-op, not an error.
- Amending quantity/price at receipt is permitted (spec edge case: "received in a quantity or
  condition that differs from what was ordered").

**State**: exactly two — *outstanding* (`received_date IS NULL`) and *complete*. There is no
status column; the timestamp is the state (FR-005).

---

## 3. `product_identifiers`

Every coded name for a product, of a stated kind. This is the table FR-007, FR-009, FR-014, and
FR-018 all turn on.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Integer` PK autoincrement | no | |
| `product_id` | `Integer` FK → `products.id` `ON DELETE CASCADE` | no | Indexed. |
| `id_type` | `String(20)` | no | `IdentifierType` enum: `MPN`, `GTIN`, `VENDOR`, `DISTRIBUTOR`, `INTERNAL`. |
| `value` | `String(128)` | no | **Stored in normalized form** — for `GTIN` this is the 14-digit key (research §3). |
| `vendor` | `String(200)` | yes | Scope for `VENDOR`/`DISTRIBUTOR` types; a vendor item id is only meaningful within its vendor. |
| `validation_overridden` | `Boolean` | no | Default `False`. `True` when the operator deliberately stored a value that failed check-digit validation (FR-010). |
| `date_added` | `DateTime` | no | |

**Constraints**

- `UniqueConstraint('id_type', 'value', 'vendor', name='uq_identifier_type_value_vendor')` —
  this single index is what makes FR-009 ("equivalent forms resolve to a single product") and
  the Identifier entity's "points to at most one product" true at the database level rather than
  by convention. Because GTINs are normalized before write, `012345678905` and `0012345678905`
  collide here by construction.
- Index on `value` alone — scan resolution looks up by value before knowing the type.

**Validation**

- `GTIN` values are normalized and check-digit validated (research §3); failure is rejected unless
  the operator sets `validation_overridden`, and an all-zero key is refused outright (wedge
  no-read) with **no override available**.
- `INTERNAL` values match `^WIT[0-9A-HJKMNP-TV-Z]{10}$` and are generated by the system, never
  entered by hand.
- `VENDOR`/`DISTRIBUTOR` require `vendor` to be set — that is what scopes them.

**Why `vendor` is in the unique key**: FR-008 requires that a vendor reusing an item identifier
for a different product cannot corrupt the catalogue. Scoping by vendor is half of that; the
other half is that `products.id` never derives from this table, so the worst case is a duplicate
identifier row to resolve, not two products silently merged.

---

## 4. `tags` and `product_tags`

Free-form labels cutting across categories (FR-031).

**`tags`**

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Integer` PK | no | |
| `name` | `String(64)` | no | Unique, stored lowercase-normalized. |

**`product_tags`**

| Column | Type | Null | Notes |
|---|---|---|---|
| `product_id` | `Integer` FK → `products.id` `ON DELETE CASCADE` | no | Composite PK part 1. |
| `tag_id` | `Integer` FK → `tags.id` `ON DELETE CASCADE` | no | Composite PK part 2. |

Tags are created inline the same way categories are. A tag with no products left is harmless and
is not garbage-collected on a schedule — Principle I; if unused tags ever clutter the filter UI,
that is the point to add a cleanup, with the clutter as the measurement.

---

## 5. Categories

**No table.** A category is the `products.category_path` string (research §6). Category listing is
`SELECT DISTINCT category_path FROM products`; subtree filtering is
`category_path = :p OR category_path LIKE :p || '/%'`; rename is an `UPDATE` over that same
predicate.

The consequence, stated plainly: an empty category cannot exist. Creating a category means typing
it on a product, and removing the last product in a category removes the category. For this
workshop that is the correct behaviour — a taxonomy node with nothing in it has no purpose — and
it removes an entire table, its CRUD, and its orphan-cleanup story.

---

## 6. `product_attachments`

Supporting files on a product or a purchase (FR-034). **Reuses the existing `photos` table** for
the bytes (research §7).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Integer` PK | no | |
| `photo_id` | `Integer` FK → `photos.id` `ON DELETE CASCADE` | no | The stored bytes, already supporting PDF + thumbnails. |
| `product_id` | `Integer` FK → `products.id` `ON DELETE CASCADE` | yes | |
| `purchase_id` | `Integer` FK → `purchases.id` `ON DELETE CASCADE` | yes | |
| `display_order` | `Integer` | no | Default `0`. |
| `created_at` | `DateTime` | no | |

**Constraint**: `CheckConstraint('(product_id IS NOT NULL) <> (purchase_id IS NOT NULL)')` —
exactly one owner. An attachment belongs to a product **or** a purchase, never both and never
neither.

---

## 7. Derived state — computed, never stored

Per research §10, these have **no columns**. They are named here because tasks and tests refer to
them.

| Name | Definition |
|---|---|
| `is_on_order` | `EXISTS (SELECT 1 FROM purchases WHERE product_id = p.id AND received_date IS NULL)` (FR-028) |
| `is_threshold_low` | `quantity IS NOT NULL AND reorder_threshold IS NOT NULL AND quantity <= reorder_threshold` (FR-026) |
| `is_manually_low` | `stock_status IN ('low','out')` (FR-025) |
| `is_effectively_low` | `is_threshold_low OR is_manually_low` — the reorder view's membership test (FR-027) |
| `latest_price` | `unit_price` of the most recent purchase by `order_date` (FR-006) |
| `quantity_age` | `now() - quantity_updated_at`, rendered relative (FR-024) |

---

## 8. Enums (`app/models.py`)

```text
IdentifierType : MPN | GTIN | VENDOR | DISTRIBUTOR | INTERNAL
ScanKind       : INTERNAL | ECIA | GTIN | VENDOR | FREE_TEXT
StockStatus    : LOW | OUT            (NULL is the third, absent state)
```

`ScanKind.VENDOR` is produced by resolution, not by the pure classifier — see
[scan-contract.md](./contracts/scan-contract.md) and research §5.

---

## Migrations

Roughly six revisions, each independently reversible, applied via `python manage.py db upgrade`
(Constitution V). Splitting them by table rather than shipping one large revision keeps each
`downgrade` small enough to actually exercise.

1. `products`
2. `purchases` (FK → products)
3. `product_identifiers` (FK → products, unique index)
4. `tags` + `product_tags`
5. `product_attachments` (FKs → photos, products, purchases)
6. Indexes added for search/filter paths, once the query shapes are settled

**MariaDB ordering rule** (Constitution V, and the subject of a past bug per `git log`): every
`downgrade` drops indexes and foreign keys **before** the tables or columns they depend on.
Each revision's `downgrade` must be run against a real MariaDB — SQLite will not catch the
ordering fault.

**Testing**: unit tests exercise the models on SQLite in-memory through `tests/conftest.py`;
migration up/down round-trips are exercised against MariaDB. SQLite does not enforce the
`CheckConstraint`s or FK cascades the same way, so any test asserting a constraint *rejects*
something must run where the constraint is real.
