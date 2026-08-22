"""add purchases.supplier_order_reference

Revision ID: f3d21c9a4e10
Revises: b1a0c0d10010
Create Date: 2026-08-22 12:00:00.000000

The supplier's order number -- ECIA data identifier ``1K``, which for DigiKey is
the sales order number. ``purchases.order_reference`` already holds the
*customer's* order number (``K``); these are two different numbers printed side
by side on the same bag label, and one column cannot mean both.

This is the whole schema change for feature 024. There is no ``digikey_orders``
table because a captured order is not a second record: it *is* the set of
purchases carrying its number. Which lines an order has, how many are still
outstanding, whether a line was already captured and which line a scanned bag
belongs to all answer from this column plus ones that already exist. The reorder
list already works this way and the user manual already sells the property --
"nothing on this page is stored; it is all derived when you open it, so it cannot
drift out of step with your purchases".

``1K`` has been parsed since the first release: ``app/utils/ecia.py`` extracts it
and ``CatalogService.resolve_scan`` already calls it
``supplier_order_reference``. It had nowhere to go, so it was rendered into a
free-text note on the product. The name here is that existing name; what is new
is a column to put it in. Note that ``specs/001-product-catalog/data-model.md``
claims ``order_reference`` is "also filled from ECIA K / 1K" -- only ``K`` ever
reached it, and that claim is corrected as part of this feature.

**Indexed, and the index is not speculative.** It is half the key every receiving
scan looks up by: a label's ``1K`` names the order and its ``P`` names the line
within it. The other half, ``vendor_item_id``, has been indexed since feature
001. At ``String(200)`` under utf8mb4 this is 800 bytes, comfortably inside
InnoDB's 3072-byte key limit.

**Nothing is backfilled.** A purchase recorded before this feature has no sales
order number to recover -- not in ``notes``, where a scanned value may have
landed as prose, and not anywhere else. Parsing notes to guess would write
fabricated references that are indistinguishable from real ones afterwards.

The reverse drops the index first and then the column, in that order, because
MariaDB will not drop a column an index still covers. It loses every recorded
sales order number and nothing else: the purchases, their products and their
received state are untouched, so downgrading returns the catalog to a state where
a scanned bag no longer finds its order line and falls back to the part-based
behaviour it had before.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3d21c9a4e10'
down_revision: Union[str, None] = 'b1a0c0d10010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'purchases',
        sa.Column('supplier_order_reference', sa.String(length=200), nullable=True)
    )
    op.create_index(
        'ix_purchases_supplier_order_reference',
        'purchases',
        ['supplier_order_reference']
    )


def downgrade() -> None:
    # Index first: MariaDB refuses to drop a column an index still covers.
    op.drop_index('ix_purchases_supplier_order_reference', table_name='purchases')
    op.drop_column('purchases', 'supplier_order_reference')
