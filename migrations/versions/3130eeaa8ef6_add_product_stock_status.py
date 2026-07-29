"""add product stock status

Revision ID: 3130eeaa8ef6
Revises: d4f18b0a6c37
Create Date: 2026-07-29 14:02:11.377145

Story 5.3 — Manual stock status. Adds TWO columns to `products` and nothing
else.

`stock_status` holds the operator's MANUAL assertion about a product's stock
(FR28/FR29): one of `unknown` / `ok` / `low` / `out`, single-sourced as
`app.models.StockStatus` and stored as the string. Nothing derived ever writes
it (AD-6). It is NOT NULL with `server_default='unknown'`, and both halves of
that are deliberate:

* The server default IS the backfill. Every existing row reads `unknown` the
  moment this `ALTER TABLE` returns, so there is no data migration to write and
  no window in which the column is NULL. `unknown` is the honest value for a row
  nobody has asserted anything about — it is the ABSENCE of an opinion, not a
  fourth one.
* NOT NULL is what keeps the read predicate two-valued. `Product
  .is_effective_low` (FR30) is now `stock_status IN ('low','out') OR
  (quantity_on_hand IS NOT NULL AND reorder_threshold IS NOT NULL AND
  quantity_on_hand <= reorder_threshold)`, and `IN` against a NULL column is
  NULL rather than FALSE — `OR(NULL, FALSE)` is NULL, so `NOT (…)` would drop
  every un-asserted row from both halves of the partition. A nullable column
  here would need its own `coalesce` guard; a non-nullable one has no failure
  mode to guard.

No CHECK constraint and no `sa.Enum`, matching how `product_identifiers
.identifier_type` stores `IdentifierType`: the closed set lives in Python so a
later story can extend it without a migration, and MariaDB's `ENUM` would make
adding a value a schema change.

`stock_status_at` records when that assertion last CHANGED (FR31), so its AGE
can be shown beside the status rather than the staleness being silently
corrected — the same contract, and the same nullable shape, as
`quantity_verified_at`. It is NULL exactly when the status is `unknown`.
CatalogService is its only writer. Nothing on the purchase/receipt path touches
either column; Story 5.5 is what teaches a receipt to clear a manual low.

`stock_status` DECLARES its collation, and is the one place this story departs
from `2c837402a89a`'s rule that an added string column simply inherits the
table default. `ALTER TABLE ... ADD COLUMN` would give it utf8mb4 /
utf8mb4_unicode_ci, which `a977ca7315df` pinned for `products` — a collation
that folds case AND accents. That is right for operator-typed prose
(`description`, `location`, `category_path`) and wrong here, because this
column is a CLOSED MACHINE VOCABULARY that a read predicate compares against:
under the folding default, `stock_status IN ('low','out')` is TRUE on the
server for a row storing `'LOW'`, `'Low'` or `'lòw'`, while
`Product.is_effective_low`'s Python getter — a frozenset membership test — is
FALSE for all three. The two encodings AD-6 requires to agree row for row would
then disagree on exactly the rows a hand-run UPDATE or a restored backup
produces, invisibly, since SQLite compares binary anyway. `utf8mb4_bin` makes
all three agree, and folding buys nothing on a four-value vocabulary the write
path only ever spells one way.

One case is deliberately left open. `utf8mb4_bin` is PAD SPACE on MariaDB, so a
stored `'low '` still compares equal to `'low'` server-side (verified on MariaDB
11.8). `utf8mb4_nopad_bin` would close it, at the cost of making this the
schema's only NO PAD column and splitting the single `utf8mb4_bin` pin the
schema guards share — for a spelling no writer produces. The remainder is pinned
by a test rather than left to be rediscovered.

This is the SAME class of bug, and the same fix, as `products.internal_id`
(DW-73), which `a977ca7315df` pinned to `utf8mb4_bin` for a case-sensitive
generated identifier. Those two columns are now the only exceptions to the
table default, in the migrated schema and in the `create_all` one alike:
`app/database.py` declares this column with the identical `.with_variant()`
shape, so the two continue to describe one schema and
`test_migrated_schema_matches_the_orm_metadata` continues to see no diff.
`product_identifiers.value`, the tag paths and the category paths keep folding
— their duplicate rejections are written against it.

`stock_status_at` is a DATETIME and has no collation to declare.

Effective Low STILL gets no column, no cache, no trigger and no index. It is
derived at read in the one place `Product.is_effective_low` expresses it (AD-6),
and this story deliberately adds no index either: it adds no query consumer (the
only read surface is one detached instance on the product detail page — Story
5.6 lands the first list), `stock_status` is a four-value low-cardinality
column, and the OR'd threshold branch is an inter-column comparison that forces
a scan regardless. A generated/virtual column carrying the predicate would be a
stored derived value, which AD-6 forbids outright.

Metal stock tables are untouched (NFR9, AD-14): two `op.add_column` calls on one
table, no data migration and no constraint anywhere.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3130eeaa8ef6'
down_revision: Union[str, None] = 'd4f18b0a6c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The `.with_variant()` shape is copied verbatim from `app/database.py`'s
    # declaration of the same column, and from `internal_id`'s before it: a bare
    # `collation='utf8mb4_bin'` would render the COLLATE clause on every
    # dialect, and both server dialect names are needed because a
    # `mariadb+pymysql://` URL reports `dialect.name == 'mariadb'` while a
    # `mysql+pymysql://` one reports `'mysql'`.
    op.add_column('products',
                  sa.Column('stock_status',
                            sa.String(length=32).with_variant(
                                sa.String(length=32,
                                          collation='utf8mb4_bin'),
                                'mysql', 'mariadb'),
                            nullable=False, server_default='unknown'))
    op.add_column('products',
                  sa.Column('stock_status_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Dropped in the reverse of the order they were added, purely for symmetry —
    # the two columns are independent of every other table. The stored
    # assertions and their dates are discarded, which is what a downgrade of an
    # additive revision means: there is nowhere else in the schema to keep them.
    # Nothing derived has to be unwound with them — Effective Low was never
    # stored, so removing these columns narrows the signal back to its threshold
    # branch rather than leaving a stale copy of it behind.
    op.drop_column('products', 'stock_status_at')
    op.drop_column('products', 'stock_status')
