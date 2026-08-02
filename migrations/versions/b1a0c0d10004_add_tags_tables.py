"""add tags and product_tags tables

Revision ID: b1a0c0d10004
Revises: b1a0c0d10003
Create Date: 2026-08-02 16:03:00.000000

Free-form labels cutting across categories (FR-031). There is deliberately no
cleanup of tags left with no products: an unused tag is harmless, and if they
ever clutter the filter UI that clutter is the measurement that justifies adding
one.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10004'
down_revision: Union[str, None] = 'b1a0c0d10003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_tags_name'),
    )
    op.create_table(
        'product_tags',
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name='fk_product_tags_product_id', ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['tag_id'], ['tags.id'],
            name='fk_product_tags_tag_id', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('product_id', 'tag_id'),
    )


def downgrade() -> None:
    # Both foreign keys go before either table; product_tags goes before tags,
    # which it references.
    op.drop_constraint('fk_product_tags_tag_id', 'product_tags', type_='foreignkey')
    op.drop_constraint('fk_product_tags_product_id', 'product_tags', type_='foreignkey')
    op.drop_table('product_tags')
    op.drop_constraint('uq_tags_name', 'tags', type_='unique')
    op.drop_table('tags')
