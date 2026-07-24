"""add products.internal_id

Revision ID: 5aeb89e22451
Revises: 3beb9dff5e41
Create Date: 2026-07-24 15:00:00.000000

Story 2.4 — Internal identifier generation and GS1 AI-96 encoding. Adds the
UNIQUE, NOT NULL products.internal_id business key used for labels, scan lookup
and direct URLs (FR12, AD-3). The column deliberately carries NO server default:
CatalogService.create_product is the sole writer (AD-8). Existing Products are
backfilled with a generated id AND its derived INTERNAL product_identifiers row
(vendor_scope='' — INTERNAL is global, AD-9) before NOT NULL and the UNIQUE
constraint are applied, so no pre-existing row blocks the upgrade. A Product
that already carries one canonical global INTERNAL row adopts its value instead;
anything ambiguous (several such rows, or a value that is not a canonical id)
aborts the migration rather than being guessed at. Metal stock tables are
untouched (NFR9, AD-14).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# env.py puts the project root on sys.path, so the pure generator/validator the
# service uses is reused here — the backfill cannot drift from runtime issuance.
from app.utils.internal_id import generate_internal_id, is_valid_internal_id


# revision identifiers, used by Alembic.
revision: str = '5aeb89e22451'
down_revision: Union[str, None] = '3beb9dff5e41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Bound on the backfill's regeneration loop, mirroring the service's
# INTERNAL_ID_MAX_ATTEMPTS: unreachable at a ~1.1e15 candidate space, but a
# degenerate generator must fail the migration, not hang it.
_MAX_CANDIDATE_ATTEMPTS = 5

# Only globally-scoped INTERNAL rows are the derived index (AD-9); a scoped one
# lives outside the (identifier_type, value, vendor_scope) unique constraint, so
# it can neither collide with nor stand in for the derived row.
_GLOBAL_SCOPE = ''


# Lightweight table stubs for the data-migration statements (never reflect the
# ORM here: this migration must keep working when the model moves on).
_products = sa.table(
    'products',
    sa.column('id', sa.Integer),
    sa.column('internal_id', sa.String),
)
_identifiers = sa.table(
    'product_identifiers',
    sa.column('product_id', sa.Integer),
    sa.column('identifier_type', sa.String),
    sa.column('value', sa.String),
    sa.column('vendor_scope', sa.String),
    sa.column('created_at', sa.DateTime),
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Read and validate the pre-existing global INTERNAL rows BEFORE any DDL
    # is issued. Ordering matters: MySQL/MariaDB commits DDL implicitly, so an
    # abort raised after op.add_column() would leave the column applied while
    # alembic_version still points at the old revision — the re-run the error
    # message asks for would then die on 'Duplicate column name'. Validating
    # first keeps every reachable abort path a genuine no-op on the schema.
    #
    # Only globally-scoped rows are read. A vendor-scoped INTERNAL row is not
    # the derived index and is invisible to the runtime collision check (which
    # matches the constraint exactly, scope included), so adopting one would
    # both break the AD-9 global-scope invariant and hide a real integrity
    # error behind a fabricated collision later.
    existing_rows = list(bind.execute(
        sa.text("SELECT product_id, value FROM product_identifiers "
                "WHERE identifier_type = 'INTERNAL' AND vendor_scope = :scope")
        .bindparams(scope=_GLOBAL_SCOPE)))

    # A Product that already carries a global INTERNAL row (add_identifier
    # allowed that before Story 2.4 closed it) adopts THAT value as its
    # internal_id instead of getting a second, disagreeing row — the column and
    # its derived index must never disagree, which is the whole point of the new
    # guard.
    #
    # Adoption is refused rather than guessed at in the two cases where no
    # single answer exists:
    #
    #  - More than one global INTERNAL row on one Product. Promoting one would
    #    silently leave the others permanently disagreeing with the column.
    #  - A value that is not a canonical issued id. It would become an
    #    authoritative business key that gs1.encode() cannot render (a space or
    #    non-ASCII character raises), so that Product's label could never be
    #    printed — a failure that would only surface at the label printer.
    #
    # Both are believed vacuous (INTERNAL rows were never part of any released
    # workflow), so failing loudly costs nothing and destroys nothing: nothing
    # has been written or altered at this point, so the operator resolves the
    # row by hand and re-runs from a completely untouched schema.
    adopted = {}
    for product_id, value in existing_rows:
        if product_id in adopted:
            raise RuntimeError(
                f'Product {product_id} carries more than one global INTERNAL '
                f'identifier row; resolve them by hand before migrating.')
        if not is_valid_internal_id(value):
            raise RuntimeError(
                f'Product {product_id} carries a global INTERNAL identifier '
                f'row whose value {value!r} is not a canonical internal id; '
                f'resolve it by hand before migrating.')
        adopted[product_id] = value

    # 2. Add nullable so existing rows survive the DDL.
    op.add_column('products',
                  sa.Column('internal_id', sa.String(length=32), nullable=True))

    # 3. Backfill. Track issued values in-process as well as the ones read
    # above: the UNIQUE constraint is not in place yet, so nothing else would
    # catch a duplicate drawn twice within this one batch.
    issued = {row[1] for row in existing_rows}
    product_ids = [row[0] for row in
                   bind.execute(sa.text('SELECT id FROM products ORDER BY id'))]
    for product_id in product_ids:
        candidate = adopted.get(product_id)
        if candidate is None:
            # Bounded, like the service's INTERNAL_ID_MAX_ATTEMPTS: a generator
            # that cannot produce a free value fails the migration loudly
            # instead of spinning forever mid-DDL. This is the one abort that
            # cannot be hoisted ahead of the DDL — it depends on values drawn
            # during the backfill — but it requires a broken generator, not any
            # state of the data.
            for _attempt in range(_MAX_CANDIDATE_ATTEMPTS):
                candidate = generate_internal_id()
                if candidate not in issued:
                    break
            else:
                raise RuntimeError(
                    f'Could not generate a unique internal_id for product '
                    f'{product_id} after {_MAX_CANDIDATE_ATTEMPTS} attempts.')
            # The derived INTERNAL index row is written from the SAME value in
            # the same migration step, exactly as create_product does at
            # runtime. Products that adopted an existing row already have one.
            bind.execute(_identifiers.insert().values(
                product_id=product_id,
                identifier_type='INTERNAL',
                value=candidate,
                vendor_scope=_GLOBAL_SCOPE,
                created_at=sa.func.now(),
            ))
        issued.add(candidate)

        bind.execute(_products.update()
                     .where(_products.c.id == product_id)
                     .values(internal_id=candidate))

    # 4. Now that every row has a value, tighten the column and add UNIQUE.
    op.alter_column('products', 'internal_id',
                    existing_type=sa.String(length=32), nullable=False)
    op.create_unique_constraint('uq_products_internal_id', 'products',
                                ['internal_id'])


def downgrade() -> None:
    op.drop_constraint('uq_products_internal_id', 'products', type_='unique')
    # Delete only the derived rows: global scope, and owned by the Product whose
    # internal_id they mirror. Matching on value alone would delete an INTERNAL
    # row belonging to a DIFFERENT product that happened to hold the same
    # string, which this revision never created.
    #
    # A row that upgrade() *adopted* is indistinguishable from one it inserted
    # (that is what adoption means — the column and the row now agree), so it is
    # removed too. Nothing else is: a vendor-scoped INTERNAL row, or one whose
    # value disagrees with its Product's column, is left untouched.
    op.execute(sa.text(
        "DELETE FROM product_identifiers "
        "WHERE identifier_type = 'INTERNAL' AND vendor_scope = '' "
        "AND EXISTS (SELECT 1 FROM products p "
        "            WHERE p.id = product_identifiers.product_id "
        "              AND p.internal_id = product_identifiers.value)"))
    op.drop_column('products', 'internal_id')
