"""Add precision field to inventory items

Revision ID: add_precision_field
Revises: dce1254cd381
Create Date: 2025-09-25 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_precision_field'
down_revision: Union[str, None] = 'dce1254cd381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add precision field to inventory_items table
    op.add_column('inventory_items', 
                  sa.Column('precision', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove precision field from inventory_items table
    op.drop_column('inventory_items', 'precision')