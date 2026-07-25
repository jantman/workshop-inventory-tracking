"""add product_tags table

Revision ID: 68707d1f48bf
Revises: f8e66632ee42
Create Date: 2026-07-24 22:27:44.910403

Story 3.3 — Free-form tags. Stores zero or more canonical free-form tags per
Product (FR16), independent of products.category_path, with DB-enforced
uniqueness of a tag per Product over (product_id, tag). There is no global tag
vocabulary table: the vocabulary is the distinct set of assigned tag values.
Metal stock / products / purchases / identifiers / attachments untouched
(NFR9, AD-14).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68707d1f48bf'
down_revision: Union[str, None] = 'f8e66632ee42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('tag', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'tag',
                            name='uq_product_tags_product_tag'),
    )
    op.create_index(op.f('ix_product_tags_product_id'), 'product_tags', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_tags_tag'), 'product_tags', ['tag'], unique=False)


def downgrade() -> None:
    # Single drop_table only. The product_id index backs a live FK, and MariaDB
    # refuses to DROP INDEX while an FK depends on it. DROP TABLE removes the FK,
    # indexes, unique constraint, and table atomically.
    op.drop_table('product_tags')
