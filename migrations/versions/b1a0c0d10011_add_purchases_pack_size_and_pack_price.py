"""add purchases.pack_size and purchases.pack_price

Revision ID: b1a0c0d10011
Revises: d0817b3ea45c
Create Date: 2026-09-19 18:00:00.000000

What the vendor charged, where it sold a pack rather than an item.

**This reverses a standing decision, on purpose.** Three places in the code
said pack values were not stored -- the McMaster review's packs column, the
capture confirmation page, and ``ListingCapture`` -- and that was right while a
pack was only a calculator for working out a unit price. It stopped being right
when capturing an Amazon order of multi-item packs (issue #137) had to record
items rather than listings, and when a pack size became something that can be
*guessed* from a title and therefore has to be auditable afterwards.

**Why pack_price is a column and not arithmetic.** The capture divides what the
vendor charged by the pack size and rounds to the cent, because a purchase
price is recorded to the cent: $13.23 across 100 is stored as $0.13. Going back
the other way gives $13.00. The 23 cents is destroyed by rounding the feature
performs deliberately, so nothing short of storing the figure recovers what the
card was charged. That is the measurement behind this revision rather than an
assumption.

**They are not a derivation of the row.** ``quantity`` and ``unit_price``
remain what the catalog records -- individual items, and the price of one.
These two are the vendor's own line. The pairs answer different questions and
may legitimately disagree: a pack of 100 ordered and 90 received is a true row,
and the receive screen amends the quantity while leaving these alone.

Both nullable, and they stay nullable. A purchase recorded by hand, captured
from DigiKey, or captured before this revision has no pack, and **pack_size is
never 1** -- a pack of one is no pack, and storing 1 would make every purchase
in the catalog claim to be one. NULL is what keeps "nothing was stated" and "a
pack of one was stated" distinguishable.

Numeric(10, 2) for the price, matching ``unit_price`` exactly, so the same
silent-rounding caveat applies and the same ``_validate_price`` guards it.

Neither is indexed. They are read only when a purchase is displayed, never
filtered or joined on, and an index here would be the speculative kind
Constitution I prohibits.

**Nothing is backfilled.** A purchase already recorded holds no pack and none
can be inferred -- the vendor's line is exactly the information that was
discarded. Existing rows are not rewritten, which is also what makes this
upgrade instant on a table of any size.

The reverse drops both columns. That loses the ability to restate a vendor's
line and nothing else: quantities, prices, products and received state are
untouched, and a captured order goes back to showing only what the catalog
records -- the behaviour before this revision.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10011'
down_revision: Union[str, None] = 'd0817b3ea45c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchases',
        sa.Column('pack_size', sa.Integer(), nullable=True)
    )
    op.add_column(
        'purchases',
        sa.Column('pack_price', sa.Numeric(precision=10, scale=2), nullable=True)
    )


def downgrade() -> None:
    # No index or foreign key on either, so there is no dependency order to
    # get wrong on MariaDB. Dropped in the reverse of the order added.
    op.drop_column('purchases', 'pack_price')
    op.drop_column('purchases', 'pack_size')
