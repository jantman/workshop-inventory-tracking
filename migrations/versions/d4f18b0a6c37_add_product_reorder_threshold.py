"""add product reorder threshold

Revision ID: d4f18b0a6c37
Revises: 2c837402a89a
Create Date: 2026-07-29 10:12:31.004518

Story 5.2 — Reorder threshold and derived Effective Low. Adds ONE nullable
column to `products` and nothing else.

`reorder_threshold` is the count at or below which a product reads as low
(FR26). It is nullable with no server default and no backfill because a
threshold is a per-product decision the operator makes, not a value the system
can guess: every existing row — and every row any create path writes — starts
with none. NULL and 0 are two different states here, exactly as they are for
`quantity_on_hand`: NULL means "no threshold set", while 0 is a real threshold
meaning "low only once the count reaches zero".

The signal this column feeds gets NO column of its own. Effective Low (FR30) is
`quantity_on_hand IS NOT NULL AND reorder_threshold IS NOT NULL AND
quantity_on_hand <= reorder_threshold` — later widened by Story 5.3 with the
stored manual status — and it is DERIVED at read, in the one place
`Product.is_effective_low` expresses it (AD-6). So there is deliberately
nothing here to persist it, nothing to cache it and no trigger to maintain it,
and no index either: this story adds the predicate and its single-product read
surface, not the list that would want one (Story 5.6).

No per-column charset or collation is declared, for the reason `2c837402a89a`
gives: this is an integer column, and `ALTER TABLE ... ADD COLUMN` inherits the
table's default in any case.

Metal stock tables are untouched (NFR9, AD-14): one `op.add_column` on one
table, no data migration and no constraint anywhere.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f18b0a6c37'
down_revision: Union[str, None] = '2c837402a89a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products',
                  sa.Column('reorder_threshold', sa.Integer(), nullable=True))


def downgrade() -> None:
    # The stored thresholds are discarded, which is what a downgrade of an
    # additive revision means: there is nowhere else in the schema to keep them.
    # Nothing derived has to be unwound with them — Effective Low was never
    # stored, so removing this column simply makes the signal unavailable rather
    # than leaving a stale copy of it behind.
    op.drop_column('products', 'reorder_threshold')
