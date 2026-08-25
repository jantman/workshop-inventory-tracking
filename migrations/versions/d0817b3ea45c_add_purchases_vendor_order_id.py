"""add purchases.vendor_order_id

Revision ID: d0817b3ea45c
Revises: c9e2a4d70318
Create Date: 2026-08-25 07:30:00.000000

The vendor's own opaque id for an order, where the vendor has one that is not
the order number the operator sees.

**McMaster-Carr shows no order number at all.** Reading the live site for
feature 028 turned up only the customer's *Purchase Order* string -- carried as
the `value` of an editable input, auto-generated as MMDD+SURNAME when the
customer gives none. It is the only order identifier a human sees, so it stays
what ``supplier_order_reference`` holds and what the order screen is keyed by.

But it is editable in place, behind a pencil button, and nothing makes it
unique: two orders placed on one day auto-generate the same name. Re-capture
pairs a freshly-read order to what is already recorded *by order*, so a renamed
Purchase Order would make every line read as new and confirming the review
would write a second purchase for every one of them -- duplicate rows rather
than an error.

The order's URL carries a stable, unique 24-hex id that appears nowhere on the
page. This column records it, and re-capture pairs on it first.

Nullable, and it stays nullable: a purchase recorded by hand, or captured from
DigiKey, has no such id and must go on reconciling by order number exactly as
it does now. The id is an additional, stronger key, never a replacement -- the
same two-pass shape ``order_line_number`` already uses for lines.

String(64) rather than something narrower: 24 hex characters is McMaster's
shape today, not a contract, and the column is not a key.

Not indexed, deliberately. The lookup is already narrowed by vendor and order
number, both of which are indexed, and what remains is a handful of rows
matched in Python. An index here would be the speculative kind Constitution I
prohibits.

**Nothing is backfilled.** No purchase in any deployed database was captured
from a McMaster order -- this feature is what makes that possible -- so there
is nothing to backfill from and nothing to guess.

The reverse drops the column, which loses the rename-proof pairing and nothing
else. Purchases, their products, their prices and their received state are
untouched; a McMaster order captured before the downgrade goes back to being
paired by its Purchase Order string, which is the behaviour that motivated this
column.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0817b3ea45c'
down_revision: Union[str, None] = 'c9e2a4d70318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchases',
        sa.Column('vendor_order_id', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('purchases', 'vendor_order_id')
