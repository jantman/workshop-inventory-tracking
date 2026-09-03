# Data Model: One Clock for Recorded Timestamps

**Feature**: `specs/037-fix-timestamp-clock-basis/` | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

No column is added, removed, renamed or retyped. This document is the inventory the sweep works
from: every persisted `DateTime` in `app/database.py`, which of the spec's two kinds it is, who
writes it today, and what it becomes.

## The two kinds

The spec's entities map onto the schema as a partition, not a hierarchy. Every `DateTime` column
is exactly one of:

- **Recorded event time** — the application observed a moment and wrote it down. Nobody typed it,
  nobody reads it as a wall-clock reading, and its only use is comparison: against another
  recorded time, or against now. **Basis after this feature: naive UTC from `utc_now()`.**
- **Stated calendar day** — the operator asserted a day, or accepted "today" on their behalf. It
  is displayed as a day (`%Y-%m-%d` or `%-d %b %Y`), checked against paper, and belongs to the
  operator's calendar. **Basis: unchanged, local, from `local_now()` where it is defaulted.**

A column being nullable, indexed, or dated by a vendor does not change which kind it is. The test
is what the value is *for*.

## Recorded event times

Every row below ends on `utc_now()`. Where "column default" appears, that is
`app/database.py` — the `default=`/`onupdate=` arguments move from `func.now()` to the callable.

| Table | Column | `database.py` | Written today by | Wrong today? |
|---|---|---|---|---|
| `inventory_items` | `date_added` | :78 | column default; `mariadb_inventory_service.py:637` (aware UTC) | No — but it **orders history** (R8) |
| `inventory_items` | `last_modified` | :79 | column default + onupdate; `mariadb_inventory_service.py:603,638,953,1133,1166`; `mariadb_storage.py:430` | No — three writers, one basis, by luck |
| `material_taxonomy` | `date_added` | :638 | column default; `mariadb_materials_admin_service.py:180` (**local**) | **Yes** |
| `material_taxonomy` | `last_modified` | :639 | column default + onupdate; `mariadb_materials_admin_service.py:181,250,354` (**local**); `mariadb_storage.py:442` (aware UTC) | **Yes** |
| `photos` | `created_at` | :714 | column default; `photo_service.py:118` (`utcnow`, deprecated) | No — deprecated API |
| `photos` | `updated_at` | :715 | column default + onupdate; `photo_service.py:119,873` (`utcnow`) | No — deprecated API |
| `item_photo_associations` | `created_at` | :776 | column default; `photo_service.py:133,423` (`utcnow`) | No — deprecated API |
| `products` | `date_added` | :870 | column default | No |
| `products` | `last_modified` | :871 | column default + onupdate | No |
| `products` | `quantity_updated_at` | :853 | `catalog_service.py:223,445` (**local**) — no column default | **Yes — the reported bug** |
| `products` | `stock_status_updated_at` | :866 | `catalog_service.py:499` (**local**) — no column default | **Yes — the reported bug** |
| `purchases` | `date_added` | :1119 | column default | No |
| `purchases` | `last_modified` | :1120 | column default + onupdate | No |
| `product_identifiers` | `date_added` | :1207 | column default | No |
| `product_attachments` | `created_at` | :1377 | column default | No |

Four columns are wrong today, on two tables. The other eleven are swept anyway, for the reason
R1 gives: leaving three writers in place is what produced the four.

**`products.quantity_updated_at` and `stock_status_updated_at` are the only recorded columns with
no column default.** They are nullable and semantically absent until somebody counts — "unknown
age" is a real state (`app/database.py:967,983` guard for it, and the display renders it as
unknown rather than raising). Nothing about that changes.

## Stated calendar days

Unchanged in value and in basis. Listed so the sweep can be checked against them.

| Table | Column | `database.py` | Defaulted by | Why it stays local |
|---|---|---|---|---|
| `inventory_items` | `purchase_date` | :65 | typed on the item form; never defaulted | The day the operator bought it |
| `purchases` | `order_date` | :1061 | `catalog_service.py:1151` → `local_now()`, already `.replace(hour=0, ...)` | Rendered as a day; compared against the vendor's own order date |
| `purchases` | `received_date` | :1063 | `catalog_service.py:1620` → `local_now()` | Rendered as a day; `received_date IS NULL` *is* the outstanding state |

Two further local call sites are not columns but feed them:

- `app/catalog_service.py:2072` — the `now` that `_resolve_arrival_date` falls back to. It is
  compared against an operator-stated `order_date`, so it must be on the operator's calendar.
- `app/models.py:1438` — the year supplied when a vendor page gives a bare "14 Mar". It is the
  year the operator is in.

## Derived values

| Value | Where | Change |
|---|---|---|
| `Product.quantity_age` | `app/database.py:967` | `datetime.now() - …` → `utc_now() - …` |
| `Product.stock_status_age` | `app/database.py:983` | `datetime.now() - …` → `utc_now() - …` |

Both return `Optional[timedelta]`; both keep their double `None` guard. The renderer that turns a
`timedelta` into "3 hours ago" (`app/product/routes.py`) takes the delta and does not touch a
clock, so it needs no change — including its `days < 0 → 'just now'` branch, which stays as the
guard against a future-dated row that R6 leaves in the data.

## Explicitly not persisted, explicitly not swept

Per R7 these keep `datetime.now()` and stay local: `app/logging_config.py:274,336` (audit log
lines), `app/export_service.py:457` and `app/export_schemas.py:211,220,225` (report headers and
message prefixes), `app/main/routes.py:1128` (a `last_updated` label in a response body). None is
written to a column and none is compared against one.

## Invariants the tests assert

- **INV-1** — every recorded column on a newly written row holds exactly what `utc_now()`
  returned for that write. Nothing reaches these columns from the database server, from
  `datetime.now()`, or from `datetime.utcnow()`. *(FR-001, FR-002, FR-003, FR-012)*
- **INV-2** — no value written to a recorded column carries a `tzinfo`. *(R2 — the column cannot
  keep it, and a mixed comparison is a 500)*
- **INV-3** — a defaulted calendar day is the operator's local day, not the UTC day.
  *(FR-008)*
- **INV-4** — an age is `utc_now()` minus a recorded column, and both ends share a basis, so a
  count set N hours ago renders as N hours. *(FR-007)*
- **INV-5** — no existing row is read, rewritten or migrated by this feature. *(FR-009)*

## Schema change

None. `default=`/`onupdate=` are client-side in SQLAlchemy, so moving them from a SQL expression
to a Python callable emits no DDL (R3). The `server_default=sa.func.now()` already in the
migrations for `products`, `purchases`, `product_identifiers` and `product_attachments` stays and
becomes unreachable; INV-1 is what proves it is never the value that lands (R4).

**No Alembic revision is created by this feature.**
