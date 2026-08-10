"""add products.stock_status_updated_at

Revision ID: b1a0c0d10010
Revises: b1a0c0d10009
Create Date: 2026-08-09 18:00:00.000000

When the operator's manual low/out flag was last set. Mirrors
``products.quantity_updated_at`` in shape and in purpose: the flag is evidence of
somebody looking at a shelf, and evidence with no date attached cannot be judged.

**Nothing is backfilled** (008 FR-005, SC-006). ``products.last_modified`` is the
only candidate and it is not evidence -- it moves when a description is
corrected or a receipt clears an unrelated field, none of which is somebody
looking at a shelf. Inventing a date here would reproduce inside the flag the
exact error feature 008 removes from the count, and it would be worse, because
afterwards a fabricated date is indistinguishable from a real one. So every
product already flagged reads "flagged at an unknown time" after this upgrade.
That is correct, and it is the thing most likely to be reported as a bug.

No CHECK constraint pairs the flag with its date. The identical invariant for
``quantity`` / ``quantity_updated_at`` has been enforced in code alone since
feature 001, and constraining the new pair but not the old one would leave the
table saying that one of two matching rules matters; see the feature's
``research.md``. The constraint could not have been symmetric in any case,
because a flag with no date is a legal row -- it is every row predating this.

The reverse loses every flag date and nothing else. Flags themselves, counts,
count ages and purchases are untouched, so downgrading returns the catalogue to
its previous behaviour: flags with no age.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10010'
down_revision: Union[str, None] = 'b1a0c0d10009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('stock_status_updated_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('products', 'stock_status_updated_at')
