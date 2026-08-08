"""add products.sub_location

Revision ID: b1a0c0d10006
Revises: b1a0c0d10005
Create Date: 2026-08-07 17:30:00.000000

Mirrors ``inventory_items.sub_location`` exactly. The two columns feed one shared
suggestion vocabulary, so a value storable on one side has to be storable on the
other.

NULL means "no sub-location recorded", which is an ordinary state and not an
error -- the same convention ``products.location`` already follows. Existing
products keep NULL; there is no backfill, because splitting a stored location
like ``Bin 4`` into a location/sub-location pair means guessing where the
boundary is, and a wrong guess is silent.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10006'
down_revision: Union[str, None] = 'b1a0c0d10005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('sub_location', sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('products', 'sub_location')
