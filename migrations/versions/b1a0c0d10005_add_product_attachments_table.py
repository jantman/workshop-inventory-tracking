"""add product_attachments table

Revision ID: b1a0c0d10005
Revises: b1a0c0d10004
Create Date: 2026-08-02 16:04:00.000000

Attachments reuse the existing photos table for the bytes -- it already stores
three sizes, enforces a MIME allow-list and renders PDF thumbnails, so datasheets
work with no second blob store (FR-034).

The check constraint is the point of the table: an attachment belongs to a
product or to a purchase, never both and never neither.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10005'
down_revision: Union[str, None] = 'b1a0c0d10004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_attachments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('purchase_id', sa.Integer(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            '(product_id IS NOT NULL) <> (purchase_id IS NOT NULL)',
            name='ck_attachment_exactly_one_owner'
        ),
        sa.ForeignKeyConstraint(
            ['photo_id'], ['photos.id'],
            name='fk_product_attachments_photo_id', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name='fk_product_attachments_product_id', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['purchase_id'], ['purchases.id'],
            name='fk_product_attachments_purchase_id', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_attachments_photo_id'), 'product_attachments', ['photo_id'], unique=False)
    op.create_index(op.f('ix_product_attachments_product_id'), 'product_attachments', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_attachments_purchase_id'), 'product_attachments', ['purchase_id'], unique=False)


def downgrade() -> None:
    # Every foreign key first -- each one holds its backing index open.
    op.drop_constraint('fk_product_attachments_purchase_id', 'product_attachments', type_='foreignkey')
    op.drop_constraint('fk_product_attachments_product_id', 'product_attachments', type_='foreignkey')
    op.drop_constraint('fk_product_attachments_photo_id', 'product_attachments', type_='foreignkey')
    op.drop_index(op.f('ix_product_attachments_purchase_id'), table_name='product_attachments')
    op.drop_index(op.f('ix_product_attachments_product_id'), table_name='product_attachments')
    op.drop_index(op.f('ix_product_attachments_photo_id'), table_name='product_attachments')
    op.drop_table('product_attachments')
