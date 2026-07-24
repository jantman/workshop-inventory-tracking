"""add purchases table

Revision ID: 46393d2e6c96
Revises: c10caa1431c6
Create Date: 2026-07-23 21:00:00.000000

Story 1.2 — Purchase entity and migration. Creates the `purchases` table with a
FK to `products.id` (FR1/AD-3) and a nullable UNIQUE `request_key` idempotency
column (AD-9). Metal stock and the products table are untouched (NFR9).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46393d2e6c96'
down_revision: Union[str, None] = 'c10caa1431c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'purchases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('vendor', sa.String(length=255), nullable=True),
        sa.Column('vendor_sku', sa.String(length=255), nullable=True),
        sa.Column('order_date', sa.Date(), nullable=True),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('order_number', sa.String(length=255), nullable=True),
        sa.Column('source_url', sa.String(length=1024), nullable=True),
        sa.Column('request_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_key', name='uq_purchases_request_key'),
    )
    op.create_index(op.f('ix_purchases_product_id'), 'purchases', ['product_id'], unique=False)


def downgrade() -> None:
    # Single drop_table only. ix_purchases_product_id backs the product_id
    # foreign key, and MariaDB refuses to DROP INDEX while a live FK depends on
    # it (see issue #36 / PR #44). DROP TABLE removes the FK, both indexes, and
    # the table atomically — do NOT drop the index separately first.
    op.drop_table('purchases')
