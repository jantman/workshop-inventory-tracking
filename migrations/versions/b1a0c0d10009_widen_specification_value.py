"""widen product_specifications.value to MEDIUMTEXT

Revision ID: b1a0c0d10009
Revises: b1a0c0d10008
Create Date: 2026-08-09 12:00:00.000000

A captured listing description is kept in full (FR-006), and it is stored as one
``product_specifications`` row named ``Description``. ``TEXT`` holds 65,535
**bytes** -- not characters, so multi-byte text hits the wall sooner than its
length suggests -- and MariaDB in strict mode raises on overflow. Left alone that
would refuse an over-long capture at the confirmation step, on a page the
operator cannot fix, after the listing state is already lost.

The alternative was capping the extractor at 60,000 characters. Nothing observed
would have been touched -- the largest description across the six sampled
listings was 28,767 characters -- but it buys that by writing a permanent
asterisk onto a requirement that says "kept in full", and the exception would
outlive everyone's memory of why it existed. ``MEDIUMTEXT`` holds 16,777,215
bytes, 580x the largest ever seen on these listings, and removes the exception
instead of documenting it.

Data, both ways
---------------

``upgrade`` moves no data. A widening cannot fail on existing rows, because every
existing value already fits inside the larger type. ``NOT NULL`` is restated
because MariaDB's ``MODIFY`` replaces the whole column definition and would
otherwise silently make the column nullable.

``downgrade`` is the interesting half, because narrowing is the direction that
can lose data. **It refuses rather than truncating**: it counts the rows that
would not fit and raises naming them, so the operator can shorten or delete those
rows and try again. Principle I never licenses losing data, and a downgrade that
silently truncates a specification is exactly that.

``LENGTH`` and not ``CHAR_LENGTH`` is deliberate: the type bounds bytes, and
counting characters would under-report multi-byte text into a false pass and then
a silent truncation.

That guard protects something older too. ``b1a0c0d10007``'s downgrade folds every
specification row back into the ``products.specifications TEXT`` column it
replaced, and would meet the same overflow. Alembic runs downgrades newest-first,
so this refuses before that one can run. It does not close the whole hole --
``b1a0c0d10007`` concatenates *all* of a product's rows into one ``TEXT``, so many
large rows could still overflow together -- but that is pre-existing and out of
this feature's scope.

**Neither test suite runs Alembic**, and this change is MariaDB-only besides, so
the round trip in specs/007-product-page-capture/quickstart.md is the only
coverage this revision will ever have. It is not optional.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10009'
down_revision: Union[str, None] = 'b1a0c0d10008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# What TEXT holds, in bytes. The number this whole revision is about.
TEXT_LIMIT = 65535


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "ALTER TABLE product_specifications MODIFY value MEDIUMTEXT NOT NULL"
    ))


def downgrade() -> None:
    oversized = op.get_bind().execute(sa.text(
        f"""
        SELECT id, product_id, LENGTH(value) AS bytes
          FROM product_specifications
         WHERE LENGTH(value) > {TEXT_LIMIT}
         ORDER BY bytes DESC
        """
    )).fetchall()

    if oversized:
        rows = ', '.join(
            f"specification {row.id} on product {row.product_id} ({row.bytes} bytes)"
            for row in oversized
        )
        raise RuntimeError(
            f"Refusing to narrow product_specifications.value back to TEXT: "
            f"{len(oversized)} row(s) hold more than {TEXT_LIMIT} bytes and would "
            f"be truncated -- {rows}. Shorten or delete them and run the downgrade "
            f"again."
        )

    op.get_bind().execute(sa.text(
        "ALTER TABLE product_specifications MODIFY value TEXT NOT NULL"
    ))
