"""add attachments table

Revision ID: f771284e1478
Revises: 46393d2e6c96
Create Date: 2026-07-24 12:00:00.000000

Story 1.5 — Attachments on product or purchase. BLOB-in-DB attachment owned by
exactly one of a Product or a Purchase (AD-12), enforced by the XOR CHECK.
Metal stock / products / purchases untouched (NFR9).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'f771284e1478'
down_revision: Union[str, None] = '46393d2e6c96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('purchase_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, 'mysql'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('(product_id IS NULL) <> (purchase_id IS NULL)', name='ck_attachment_one_owner'),
        sa.CheckConstraint('file_size > 0', name='ck_attachment_positive_file_size'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_attachments_product_id'), 'attachments', ['product_id'], unique=False)
    op.create_index(op.f('ix_attachments_purchase_id'), 'attachments', ['purchase_id'], unique=False)


def downgrade() -> None:
    # Single drop_table only. The product_id/purchase_id indexes back live FKs,
    # and MariaDB refuses to DROP INDEX while an FK depends on it (issue #36 /
    # PR #44). DROP TABLE removes the FKs, indexes, and table atomically.
    op.drop_table('attachments')
