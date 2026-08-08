"""structured product specifications

Revision ID: b1a0c0d10007
Revises: b1a0c0d10006
Create Date: 2026-08-08 08:00:00.000000

``products.specifications TEXT`` becomes a child table of ``(name, value,
display_order)`` rows, so "every 12 V converter I own" is a filter rather than a
substring search that also matches a description mentioning 12 V.

Every existing paragraph is carried across **verbatim** as a single row named
``Specifications`` -- never split at a newline, a colon or a comma. A paragraph
reading ``Voltage: 12 V`` is one operator-authored block of prose that happens to
contain a colon, and a splitter would turn it into a name and a value that the
operator never wrote. A NULL or whitespace-only paragraph carries across as no
row at all, which is the same "not recorded" state it already meant.

Both data steps run as Python loops over ``op.get_bind()`` with bound parameters
rather than as one dialect-specific statement. The join on the way down is the
reason: MariaDB spells ordered concatenation ``GROUP_CONCAT(x ORDER BY y
SEPARATOR '\\n')`` and SQLite's ``group_concat`` takes no ``ORDER BY`` at all.
Maintaining two spellings to save a loop over tens of rows would be a poor trade
anywhere, and this is the one step in the feature that cannot be re-run to fix a
mistake.

There is deliberately no ``UniqueConstraint('product_id', 'name')``. Under the
deployed collation (``utf8mb4_uca1400_ai_ci``) it would reject ``Volt`` against
``Vôlt``, which the requirement permits; under SQLite's BINARY it would accept
``Voltage`` against ``voltage``, which the requirement forbids. A constraint that
means two different things on two backends is worse than none, and the invariant
is cosmetic rather than integrity -- a product with two ``Voltage`` rows is
untidy, never corrupt. ``CatalogService._validate_specifications`` is the
authority.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a0c0d10007'
down_revision: Union[str, None] = 'b1a0c0d10006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The name given to a paragraph carried across from the old column. The
# downgrade recognizes it to restore the original text unchanged, so the two
# directions have to agree on the spelling.
LEGACY_NAME = 'Specifications'


def upgrade() -> None:
    op.create_table(
        'product_specifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        # Text, not String: this has to hold anything the old column held,
        # including a multi-line paragraph.
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name='fk_product_specifications_product_id', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_product_specifications_product_id'),
        'product_specifications', ['product_id'], unique=False
    )
    # The filter looks products up by specification name.
    op.create_index(
        op.f('ix_product_specifications_name'),
        'product_specifications', ['name'], unique=False
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, specifications FROM products WHERE specifications IS NOT NULL"
    )).fetchall()

    insert = sa.text(
        "INSERT INTO product_specifications (product_id, name, value, display_order) "
        "VALUES (:product_id, :name, :value, 0)"
    )
    carried = 0
    for product_id, paragraph in rows:
        # Whitespace-only is "not recorded", the same as NULL. It gets no row
        # rather than an empty one.
        if paragraph is None or not paragraph.strip():
            continue
        # Stored exactly as found, not stripped: the downgrade promises the
        # original text back character for character, and it can only keep that
        # promise if nothing was shaved off on the way in.
        bind.execute(insert, {
            'product_id': product_id,
            'name': LEGACY_NAME,
            'value': paragraph,
        })
        carried += 1

    print(f"Carried {carried} product specification paragraph(s) into rows")

    op.drop_column('products', 'specifications')


def downgrade() -> None:
    op.add_column('products', sa.Column('specifications', sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT product_id, name, value FROM product_specifications "
        "ORDER BY product_id, display_order, id"
    )).fetchall()

    by_product: dict = {}
    for product_id, name, value in rows:
        by_product.setdefault(product_id, []).append((name, value))

    update = sa.text("UPDATE products SET specifications = :text WHERE id = :id")
    for product_id, entries in by_product.items():
        if len(entries) == 1 and entries[0][0] == LEGACY_NAME:
            # An untouched carry-across round-trips to the exact original
            # paragraph -- no label prepended, no re-wrapping.
            paragraph = entries[0][1]
        else:
            # Anything the operator has since edited into named values becomes a
            # readable block. Structure is lost here and content is not, which
            # is the standard this direction is held to.
            paragraph = "\n".join(f"{name}: {value}" for name, value in entries)
        bind.execute(update, {'text': paragraph, 'id': product_id})

    print(f"Restored specification text for {len(by_product)} product(s)")

    # Constraint, then indexes, then the table -- the order b1a0c0d10003's
    # downgrade already establishes for this shape of table.
    op.drop_constraint(
        'fk_product_specifications_product_id', 'product_specifications',
        type_='foreignkey'
    )
    op.drop_index(
        op.f('ix_product_specifications_name'), table_name='product_specifications'
    )
    op.drop_index(
        op.f('ix_product_specifications_product_id'),
        table_name='product_specifications'
    )
    op.drop_table('product_specifications')
