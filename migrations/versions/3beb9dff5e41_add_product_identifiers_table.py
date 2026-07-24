"""add product_identifiers table

Revision ID: 3beb9dff5e41
Revises: f771284e1478
Create Date: 2026-07-24 13:00:00.000000

Story 2.1 — Typed identifier entity and uniqueness. Stores multiple typed
(identifier_type, value) identifiers per Product (FR7), with DB-enforced scoped
uniqueness over (identifier_type, value, vendor_scope) (FR8, AD-9). vendor_scope
is a NOT NULL empty-string sentinel for global types. Metal stock / products /
purchases / attachments untouched (NFR9, AD-14).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3beb9dff5e41'
down_revision: Union[str, None] = 'f771284e1478'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_identifiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('identifier_type', sa.String(length=32), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('vendor_scope', sa.String(length=255), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('identifier_type', 'value', 'vendor_scope',
                            name='uq_product_identifiers_type_value_scope'),
    )
    op.create_index(op.f('ix_product_identifiers_product_id'), 'product_identifiers', ['product_id'], unique=False)


def downgrade() -> None:
    # Single drop_table only. The product_id index backs a live FK, and MariaDB
    # refuses to DROP INDEX while an FK depends on it. DROP TABLE removes the FK,
    # indexes, unique constraint, and table atomically.
    op.drop_table('product_identifiers')
