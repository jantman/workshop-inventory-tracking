"""rename purchases.digikey_line_number to order_line_number

Revision ID: c9e2a4d70318
Revises: a7c4e1b0f221
Create Date: 2026-08-25 06:00:00.000000

The column records which line of a supplier's order a purchase came from.
It was added for DigiKey and named after it, but nothing about what it
holds is DigiKey-specific: **a part number does not identify a line**, an
order can carry the same part twice, and pairing lines to purchases
positionally corrupts data the first time that happens
(``a7c4e1b0f221``, PR #116 review).

Feature 028 captures McMaster-Carr orders read out of the page rather
than fetched from a service, which makes the case stronger rather than
weaker -- a page's line ordering is not a contract at all. So a second
vendor writes the same column, and the name becomes a lie unless it is
fixed.

A rename rather than a second nullable column meaning the same thing: two
columns for one fact is the duplication that "boring, obvious code"
exists to prevent.

Type, nullability and the absence of an index are all unchanged. Nothing
is backfilled and no value moves -- MariaDB renames the column in place,
and every existing ``digikey_line_number`` is an ``order_line_number``
already.

``a7c4e1b0f221``, which created the column, is not edited: shipped
migrations are frozen and describe what shipped.

The reverse renames it back, and loses nothing. A McMaster order captured
before a downgrade keeps its line numbers in the DigiKey-named column;
only the name is wrong, and re-upgrading fixes it.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e2a4d70318'
down_revision: Union[str, None] = 'a7c4e1b0f221'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'purchases',
        'digikey_line_number',
        new_column_name='order_line_number',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'purchases',
        'order_line_number',
        new_column_name='digikey_line_number',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
