"""add products table

Revision ID: b1a0c0d10001
Revises: 8213852b0b94
Create Date: 2026-08-02 16:00:00.000000

First of the product catalogue revisions. Split by table rather than shipped as
one large revision so that each downgrade stays small enough to actually
exercise against MariaDB (Constitution V).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10001'
down_revision: Union[str, None] = '8213852b0b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('manufacturer', sa.String(length=200), nullable=True),
        sa.Column('manufacturer_part_number', sa.String(length=100), nullable=True),
        sa.Column('specifications', sa.Text(), nullable=True),
        sa.Column('category_path', sa.String(length=512), nullable=True),
        sa.Column('location', sa.String(length=100), nullable=True),
        # Tri-state quantity (FR-022/FR-023): NULL = not tracked, 0 = none on hand.
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('quantity_updated_at', sa.DateTime(), nullable=True),
        sa.Column('reorder_threshold', sa.Integer(), nullable=True),
        sa.Column('stock_status', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('date_added', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            'last_modified', sa.DateTime(), nullable=False,
            server_default=sa.func.now(), server_onupdate=sa.func.now()
        ),
        sa.CheckConstraint('quantity IS NULL OR quantity >= 0', name='ck_product_quantity_non_negative'),
        sa.CheckConstraint(
            'reorder_threshold IS NULL OR reorder_threshold >= 0',
            name='ck_product_reorder_threshold_non_negative'
        ),
        sa.CheckConstraint(
            "stock_status IS NULL OR stock_status IN ('low','out')",
            name='ck_product_valid_stock_status'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_products_category_path'), 'products', ['category_path'], unique=False)
    op.create_index('ix_products_description', 'products', ['description'], unique=False)


def downgrade() -> None:
    # Indexes first, then the table they belong to.
    op.drop_index('ix_products_description', table_name='products')
    op.drop_index(op.f('ix_products_category_path'), table_name='products')
    op.drop_table('products')
