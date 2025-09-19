"""increase_photo_blob_column_sizes

Revision ID: dce1254cd381
Revises: 649ff0d93d25
Create Date: 2025-09-19 13:28:59.889654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dce1254cd381'
down_revision: Union[str, None] = '649ff0d93d25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter photo blob columns to use MEDIUMBLOB (16MB limit) instead of BLOB (64KB limit)
    # This supports the 20MB photo requirement with sufficient headroom
    op.execute("ALTER TABLE item_photos MODIFY COLUMN thumbnail_data MEDIUMBLOB NOT NULL")
    op.execute("ALTER TABLE item_photos MODIFY COLUMN medium_data MEDIUMBLOB NOT NULL")
    op.execute("ALTER TABLE item_photos MODIFY COLUMN original_data MEDIUMBLOB NOT NULL")


def downgrade() -> None:
    # Revert to original BLOB columns (64KB limit)
    op.execute("ALTER TABLE item_photos MODIFY COLUMN thumbnail_data BLOB NOT NULL")
    op.execute("ALTER TABLE item_photos MODIFY COLUMN medium_data BLOB NOT NULL")
    op.execute("ALTER TABLE item_photos MODIFY COLUMN original_data BLOB NOT NULL")
