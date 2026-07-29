"""add product stock and location

Revision ID: 2c837402a89a
Revises: a977ca7315df
Create Date: 2026-07-29 06:05:49.841622

Story 5.1 — Tri-state quantity and location. Adds four nullable columns to
`products` and nothing else.

`quantity_on_hand` is TRI-STATE, which is the whole point of the story and the
reason it carries no server default and no NOT NULL: NULL means "not tracked at
all", 0 means "tracked, none on hand", and N means "tracked, N on hand"
(FR23/FR24). Stock tracking is opt-in per Product, so every existing row — and
every row any later create path writes — starts NULL, and no backfill is
performed or wanted. `quantity_verified_at` records WHEN the operator last
asserted the count, so that its AGE can be displayed beside the number rather
than the number being silently corrected (FR25); CatalogService is its only
writer and moves it in lockstep with `quantity_on_hand`. Nothing on the
purchase/receipt path touches either column.

`location` / `sub_location` are VARCHAR(100), deliberately the same names and
the same width as `inventory_items.location` / `.sub_location`, because the two
tables feed ONE autocomplete vocabulary through the one existing suggestion
endpoint (FR27). Matching widths mean neither side can store a value the other's
column would truncate.

No per-column charset or collation is declared: `ALTER TABLE ... ADD COLUMN`
inherits the table's default, which the `a977ca7315df` revision pinned to
utf8mb4 / utf8mb4_unicode_ci for `products` — the same folding semantics
`app/database.py`'s table-level MYSQL_TABLE_OPTIONS declares, so the migrated
schema and the `create_all` one continue to describe one schema.
`products.internal_id` keeps its `utf8mb4_bin` exception and is untouched here.

Metal stock tables are untouched (NFR9, AD-14): four `op.add_column` calls on
one table, no data migration and no constraint anywhere.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c837402a89a'
down_revision: Union[str, None] = 'a977ca7315df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products',
                  sa.Column('quantity_on_hand', sa.Integer(), nullable=True))
    op.add_column('products',
                  sa.Column('quantity_verified_at', sa.DateTime(),
                            nullable=True))
    op.add_column('products',
                  sa.Column('location', sa.String(length=100), nullable=True))
    op.add_column('products',
                  sa.Column('sub_location', sa.String(length=100),
                            nullable=True))


def downgrade() -> None:
    # Dropped in the reverse of the order they were added, purely for symmetry —
    # these four columns are independent of one another and of every other
    # table, so nothing here depends on the order. The stored counts and
    # locations are discarded, which is what a downgrade of an additive
    # revision means: there is nowhere else in the schema to keep them.
    op.drop_column('products', 'sub_location')
    op.drop_column('products', 'location')
    op.drop_column('products', 'quantity_verified_at')
    op.drop_column('products', 'quantity_on_hand')
