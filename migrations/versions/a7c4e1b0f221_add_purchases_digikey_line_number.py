"""add purchases.digikey_line_number

Revision ID: a7c4e1b0f221
Revises: f3d21c9a4e10
Create Date: 2026-08-23 01:00:00.000000

Which line of a supplier's order a purchase came from -- DigiKey's ``DetailId``.

**A part number does not identify a line.** An order can carry the same part on
two lines, and feature 024 originally paired recorded purchases to order lines by
counting occurrences of the part number. That works only while every line for a
part was captured in one go. Capture one of two duplicated lines and re-open the
order, and the first line claims the second line's purchase: it reads as already
captured with the wrong quantity, applying a change writes it to the wrong row,
and the line that genuinely was captured reads as new and is captured again.

No heuristic recovers that pairing, because the information is not present to
recover -- which is why it is stored rather than inferred. Constitution I says
build for the requirement in front of you; it also says simplicity never
justifies risking data integrity, and this is that exception.

NULL for every purchase not captured from a DigiKey order, including a
hand-recorded one that names a sales order. Matching therefore runs in two
passes: by line number where the purchase has one, then by part number for those
that do not. A NULL row is never claimed by a line that already matched exactly.

**Nothing is backfilled.** Feature 024 is unreleased, so no purchase in any
deployed database carries a DigiKey sales order number at all; there is nothing
to backfill from and nothing to guess.

Not indexed, deliberately. The lookup narrows to one order through
``supplier_order_reference`` -- which is indexed -- and what remains is a handful
of rows matched in Python. An index here would be the speculative kind
Constitution I prohibits.

The reverse loses the line pairing and nothing else. Purchases, their products,
their prices and their received state are untouched; an order captured before the
downgrade goes back to being paired by part number, which is exactly the
behaviour that motivated this column.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c4e1b0f221'
down_revision: Union[str, None] = 'f3d21c9a4e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchases',
        sa.Column('digikey_line_number', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('purchases', 'digikey_line_number')
