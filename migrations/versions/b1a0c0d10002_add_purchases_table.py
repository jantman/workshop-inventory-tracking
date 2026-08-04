"""add purchases table

Revision ID: b1a0c0d10002
Revises: b1a0c0d10001
Create Date: 2026-08-02 16:01:00.000000

There is no status column: received_date IS NULL is the outstanding state
(FR-005), so the timestamp and the status can never disagree.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10002'
down_revision: Union[str, None] = 'b1a0c0d10001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'purchases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('vendor', sa.String(length=200), nullable=False),
        sa.Column('vendor_item_id', sa.String(length=100), nullable=True),
        sa.Column('listing_title', sa.String(length=500), nullable=True),
        sa.Column('order_date', sa.DateTime(), nullable=True),
        sa.Column('received_date', sa.DateTime(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        # Decimal, never float (Constitution III).
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('order_reference', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('date_added', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            'last_modified', sa.DateTime(), nullable=False,
            server_default=sa.func.now(), server_onupdate=sa.func.now()
        ),
        sa.CheckConstraint('quantity IS NULL OR quantity > 0', name='ck_purchase_quantity_positive'),
        sa.CheckConstraint('unit_price IS NULL OR unit_price >= 0', name='ck_purchase_price_non_negative'),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name='fk_purchases_product_id', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_purchases_product_id'), 'purchases', ['product_id'], unique=False)
    op.create_index(op.f('ix_purchases_vendor_item_id'), 'purchases', ['vendor_item_id'], unique=False)
    op.create_index(op.f('ix_purchases_received_date'), 'purchases', ['received_date'], unique=False)
    op.create_index('ix_purchases_product_order_date', 'purchases', ['product_id', 'order_date'], unique=False)


def downgrade() -> None:
    # The foreign key goes before the index that backs it, and both go before
    # the table -- MariaDB refuses to drop an index a foreign key still needs.
    op.drop_constraint('fk_purchases_product_id', 'purchases', type_='foreignkey')
    op.drop_index('ix_purchases_product_order_date', table_name='purchases')
    op.drop_index(op.f('ix_purchases_received_date'), table_name='purchases')
    op.drop_index(op.f('ix_purchases_vendor_item_id'), table_name='purchases')
    op.drop_index(op.f('ix_purchases_product_id'), table_name='purchases')
    op.drop_table('purchases')
