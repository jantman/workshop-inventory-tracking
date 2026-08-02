"""add product_identifiers table

Revision ID: b1a0c0d10003
Revises: b1a0c0d10002
Create Date: 2026-08-02 16:02:00.000000

The unique index on (id_type, value, vendor) is what makes FR-009 -- "equivalent
forms of one barcode resolve to a single product" -- a database property rather
than a convention. GTINs are normalized to their 14-digit key before write, so
012345678905 and 0012345678905 collide here by construction.

``vendor`` is NOT NULL with an empty-string default rather than nullable,
deliberately: SQL treats NULLs as distinct inside a unique index, so a nullable
column would let the same GTIN be stored twice and the constraint would enforce
nothing for exactly the identifier types that need it most.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10003'
down_revision: Union[str, None] = 'b1a0c0d10002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_identifiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('id_type', sa.String(length=20), nullable=False),
        sa.Column('value', sa.String(length=128), nullable=False),
        sa.Column('vendor', sa.String(length=200), nullable=False, server_default=''),
        sa.Column(
            'validation_overridden', sa.Boolean(), nullable=False,
            server_default=sa.text('0')
        ),
        sa.Column('date_added', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name='fk_product_identifiers_product_id', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_type', 'value', 'vendor', name='uq_identifier_type_value_vendor'),
    )
    op.create_index(op.f('ix_product_identifiers_product_id'), 'product_identifiers', ['product_id'], unique=False)
    # Scan resolution looks up by value before it knows the type.
    op.create_index(op.f('ix_product_identifiers_value'), 'product_identifiers', ['value'], unique=False)


def downgrade() -> None:
    op.drop_constraint('fk_product_identifiers_product_id', 'product_identifiers', type_='foreignkey')
    op.drop_index(op.f('ix_product_identifiers_value'), table_name='product_identifiers')
    op.drop_index(op.f('ix_product_identifiers_product_id'), table_name='product_identifiers')
    op.drop_constraint('uq_identifier_type_value_vendor', 'product_identifiers', type_='unique')
    op.drop_table('product_identifiers')
