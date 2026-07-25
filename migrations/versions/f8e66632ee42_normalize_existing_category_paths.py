"""normalize existing category paths

Revision ID: f8e66632ee42
Revises: 5aeb89e22451
Create Date: 2026-07-24 18:00:00.000000

Story 3.1 — Materialized-path categories with inline create. DATA ONLY: no
column, index or constraint changes anywhere, and no table other than
`products` is read or written (NFR9, AD-14).

Since this story, CatalogService.create_product/update_product are the sole
writers of products.category_path and normalize every value they store, so
"every stored path is canonical or NULL" holds from here forward. Rows written
before that — when the column was a plain free-text field — can still hold
`Electronics/Power/`, `electronics//power` and `electronics/power` as three
different categories, which would show up as three separate branches in the
suggestion vocabulary (which IS the distinct set of stored paths — there is no
categories table). This migration makes the invariant true retroactively by
rewriting each distinct non-canonical value to its canonical form.

The canonical form comes from the same pure util the service calls
(app/utils/category.py; env.py puts the project root on sys.path), so the
backfill cannot drift from runtime normalization (AD-4). Values that are
already canonical and NULL values are left completely untouched, and a value
that normalizes to nothing (whitespace or separators only) becomes NULL —
"no category", which is what it always meant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# env.py puts the project root on sys.path, so the normalization the service
# uses at write time is reused here — one source of truth for canonical form.
from app.utils.category import normalize_category_path


# revision identifiers, used by Alembic.
revision: str = 'f8e66632ee42'
down_revision: Union[str, None] = '5aeb89e22451'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Lightweight table stub for the data-migration statements (never reflect the
# ORM here: this migration must keep working when the model moves on).
_products = sa.table(
    'products',
    sa.column('id', sa.Integer),
    sa.column('category_path', sa.String),
)

# Max primary keys per UPDATE ... WHERE id IN (...). Well under both
# MariaDB's packet limit and SQLite's bound-parameter limit.
_UPDATE_CHUNK_SIZE = 500


def upgrade() -> None:
    bind = op.get_bind()

    # Read id + value, NOT `SELECT DISTINCT category_path`. Under MariaDB's
    # default case-insensitive collation DISTINCT folds 'Electronics/Power' and
    # 'electronics/power' into ONE arbitrary representative; if the canonical
    # spelling happens to be the survivor, the mixed-case rows never get their
    # own pass and would be left non-canonical — exactly the state this
    # migration exists to eliminate. Per-row reading is collation-independent.
    rows = bind.execute(sa.text(
        'SELECT id, category_path FROM products '
        'WHERE category_path IS NOT NULL')).fetchall()

    # Group the rows that need rewriting by their target value, so the writes
    # are one UPDATE per distinct canonical path (the vocabulary is small by
    # construction — it accretes one path at a time from product entry) while
    # the rows are still addressed by primary key.
    ids_by_canonical = {}
    skipped_ids = []
    for product_id, stored in rows:
        try:
            canonical = normalize_category_path(stored)
        except Exception:
            # A value that cannot be normalized is left exactly as it is: it
            # could not be stored canonically anyway, and one such row must
            # not abort the whole upgrade. Reachable two ways — a pre-MariaDB
            # SQLite-era row holding more than the column's 512 characters,
            # and (rarely) a row within 512 characters whose canonical form is
            # LONGER, since lowercasing can lengthen a string ('İ'.lower() is
            # two characters). Such rows stay non-canonical, so they are
            # reported below rather than passed over in silence.
            skipped_ids.append(product_id)
            continue
        if canonical == stored:
            # Already canonical — leave the row completely alone (no UPDATE at
            # all, so nothing about it is touched).
            continue
        ids_by_canonical.setdefault(canonical, []).append(product_id)

    # These UPDATEs run against the sa.table() stub above, which declares only
    # id and category_path, so `updated_at` is NOT bumped: the model's
    # onupdate=func.now() lives on the ORM Column and never sees these
    # statements. That is intended — a backfill is not an edit by the operator,
    # and nothing should look like it was touched today.
    for canonical, product_ids in ids_by_canonical.items():
        # Chunk the id list: the number of DISTINCT canonical paths is small by
        # construction (the vocabulary accretes one path at a time), but the
        # number of ROWS per path is not — a catalog with 100k products filed
        # under one miscapitalized category would otherwise build a single
        # 100k-placeholder IN clause, past MariaDB's max_allowed_packet and
        # past SQLite's variable limit.
        for offset in range(0, len(product_ids), _UPDATE_CHUNK_SIZE):
            chunk = product_ids[offset:offset + _UPDATE_CHUNK_SIZE]
            bind.execute(_products.update()
                         .where(_products.c.id.in_(chunk))
                         .values(category_path=canonical))

    if skipped_ids:
        # The upgrade still succeeds, but the "every stored path is canonical
        # or NULL" invariant does not hold for these rows and nothing else
        # will ever tell the operator: they are equally unstorable through the
        # form, so they need a manual decision.
        print(
            f'WARNING: {len(skipped_ids)} products.category_path value(s) '
            f'could not be normalized and were left unchanged '
            f'(product ids: {skipped_ids[:20]}'
            f'{", ..." if len(skipped_ids) > 20 else ""}). '
            f'Shorten or clear these categories by hand.'
        )


def downgrade() -> None:
    """Irreversible by design — a documented no-op.

    Normalization is lossy: `Electronics/Power/`, `electronics//power` and
    `electronics/power` all collapse to one canonical string, and nothing
    records which row held which spelling. There is no information from which
    to reconstruct the pre-upgrade values, and inventing one would be worse
    than leaving them canonical: the canonical form is valid input for the old
    free-text column, so downgrading the schema past this point still leaves a
    working database.
    """
    pass
