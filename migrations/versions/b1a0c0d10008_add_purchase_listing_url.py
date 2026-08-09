"""add purchases.listing_url

Revision ID: b1a0c0d10008
Revises: b1a0c0d10007
Create Date: 2026-08-08 20:30:00.000000

The listing's address gets its own column instead of living inside
``purchases.notes``.

Capture used to pass the URL as the purchase's notes, so for a captured purchase
the notes field simply *was* the URL. Two facts were sharing one column, and the
shared column is the one the receive screen renders as an editable "Notes" box --
so the address survived only until the operator used the field for notes. The
duplicate check now reads this address when a URL yields no vendor item id, and a
check that stops working the first time somebody writes a note is not a check.

**Not indexed.** The duplicate lookup narrows to one vendor and one calendar day
before comparing the address, over a table holding tens of rows. At 1000
characters of utf8mb4 the column is 4000 bytes, past InnoDB's 3072-byte index key
limit, so indexing it would mean a prefix index over the part of a URL that is
identical for every listing from one vendor.

Data, both ways
---------------

``upgrade`` recovers the URLs already written into notes. The predicate is
``notes LIKE 'http%'`` **and contains no space**: capture wrote a bare URL and
nothing else, and a notes field reading ``https://... -- arrived dented`` is
prose that happens to start with a URL, not a captured address. Copying that
whole would put the prose into the URL column. It is skipped, at the cost of that
one purchase not participating in duplicate detection -- which only ever costs a
warning that is not shown.

The backfill **copies, it does not move**: notes are left exactly as they are, so
nothing the operator wrote is destroyed and the statement is safe to re-run.

``downgrade`` folds the value back into notes before dropping the column, for
rows whose notes are empty -- which is every row this feature created, since
capture no longer writes notes at all. That is what makes the round trip
lossless rather than merely re-runnable. The one case it cannot preserve is a
post-feature purchase whose notes the operator has since written into: it keeps
the prose and loses the separate URL. Overwriting the operator's words to save an
address that is still on the vendor's site would be the worse trade.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10008'
down_revision: Union[str, None] = 'b1a0c0d10007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchases',
        sa.Column('listing_url', sa.String(length=1000), nullable=True)
    )

    op.get_bind().execute(sa.text(
        """
        UPDATE purchases
           SET listing_url = notes
         WHERE listing_url IS NULL
           AND notes LIKE 'http%'
           AND notes NOT LIKE '% %'
        """
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        """
        UPDATE purchases
           SET notes = listing_url
         WHERE listing_url IS NOT NULL
           AND (notes IS NULL OR notes = '')
        """
    ))

    op.drop_column('purchases', 'listing_url')
