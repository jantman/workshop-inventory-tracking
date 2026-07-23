"""add products table

Revision ID: c10caa1431c6
Revises: 8213852b0b94
Create Date: 2026-07-23 20:00:00.000000

Story 1.1 — Product entity and migration. Creates the minimal FR2 `products`
table alongside metal stock (NFR9). Later stories/epics extend this table with
their own chained migrations (internal_id, stock fields, equivalent_group_id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c10caa1431c6'
down_revision: Union[str, None] = '8213852b0b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('manufacturer', sa.String(length=255), nullable=True),
        sa.Column('mpn', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('category_path', sa.String(length=512), nullable=True),
        sa.Column('attributes', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_products_category_path'), 'products', ['category_path'], unique=False)


def downgrade() -> None:
    # Drop the index before the table (mirrors the material_taxonomy pattern).
    # products has no incoming FKs in Story 1.1, so ordering is straightforward;
    # Story 1.2's purchases FK will require dropping purchases before products.
    op.drop_index(op.f('ix_products_category_path'), table_name='products')
    op.drop_table('products')
