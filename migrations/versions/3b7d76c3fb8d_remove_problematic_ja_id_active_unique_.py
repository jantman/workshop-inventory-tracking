"""Remove problematic ja_id active unique constraint

Revision ID: 3b7d76c3fb8d
Revises: 5d61d892776a
Create Date: 2025-09-11 12:54:38.270708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b7d76c3fb8d'
down_revision: Union[str, None] = '5d61d892776a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration is now a no-op since the constraint was removed from the initial migration
    # This is kept for consistency with existing database instances that may have the constraint
    pass


def downgrade() -> None:
    # Re-add the constraint (note: this may fail if data violates the constraint)
    op.create_unique_constraint('uq_ja_id_active', 'inventory_items', ['ja_id', 'active'])
