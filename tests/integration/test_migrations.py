"""
Integration tests for the Alembic migration chain against a real MariaDB.

These migrations have never been executed by any test. The unit suite builds its
schema with ``Base.metadata.create_all`` on SQLite, which exercises the *models*
and skips the migrations entirely, so an upgrade that only fails on InnoDB (an
implicit DDL commit mid-abort, an index over the key-length limit, a correlated
DELETE MySQL rejects in the ``UPDATE ... WHERE ... SELECT FROM same table`` form)
would ship green. The runner below is deliberately generic: `test_upgrade_...`
and `test_downgrade_to_base_...` cover every revision that exists now and every
one added later, and the Story 2.4 cases underneath cover the one migration that
carries a *data* backfill rather than pure DDL.

Every test starts from `blank_database`, so file order and single-file runs give
identical results.
"""

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.database import Base
from app.utils.internal_id import is_valid_internal_id
from tests.integration.conftest import alembic_config

# The revision that introduced product_identifiers -- the state Story 2.4's
# backfill migrates *from*, and the target its downgrade returns to.
BEFORE_INTERNAL_ID = '3beb9dff5e41'
# Story 2.4 itself: products.internal_id + the derived INTERNAL identifier rows.
INTERNAL_ID_REVISION = '5aeb89e22451'

# A canonical issued id planted on P2 before the migration runs, so the adoption
# branch is taken rather than the generate branch. It must satisfy
# is_valid_internal_id or the migration aborts by design (see the revision's
# docstring), which is a different test than this one.
ADOPTED_INTERNAL_ID = 'ADPTED1234'

# A vendor-scoped INTERNAL row on P3. Deliberately NOT a canonical id: a scoped
# row is outside uq_product_identifiers_type_value_scope's global namespace, is
# invisible to the runtime collision check, and must be neither adopted by the
# upgrade nor deleted by the downgrade. Making it obviously non-canonical means
# a test that wrongly adopted it would fail loudly rather than silently pass.
VENDOR_SCOPED_VALUE = 'legacy-vendor-row'
VENDOR_SCOPE = 'Acme Distribution'

# Diff kinds `compare_metadata` may report that this drift check deliberately
# IGNORES, and why: 'modify_type' (MariaDB reflects e.g. sa.JSON as LONGTEXT and
# Boolean as TINYINT, so a faithful column reads back as a different type),
# 'modify_default' / 'modify_nullable' / 'modify_comment' (server-side default
# rendering differs from the Python-side default the models declare), and the
# index/constraint families 'add_index', 'remove_index', 'add_constraint',
# 'remove_constraint', 'add_fk', 'remove_fk' (MariaDB auto-creates an index for
# every FK and materializes a UNIQUE constraint as a unique index, so both sides
# disagree about the same object). What is NOT ignored is the class of difference
# with no benign reflection explanation: a table or column present on one side
# and absent on the other. Be clear about the cost of the ignore-list -- because
# 'modify_type' and 'modify_nullable' are discarded to suppress that reflection
# noise, a migration that gave a column a narrower type than the model declares,
# or left it nullable where the model says NOT NULL, passes this check. Those
# would have to be caught by the hand-maintained assertions below or by review.
STRUCTURAL_DIFF_KINDS = frozenset(
    {'add_table', 'remove_table', 'add_column', 'remove_column'})

# Because the drift check above is blind to constraints, the unique constraints
# the rest of this tier's behavior rests on are asserted by name instead. Both
# are load-bearing and neither is reachable from the other tests, which build
# their schema with create_all rather than by migrating: a migration that
# created one over the wrong columns -- or not at all -- would otherwise ship
# green while create_product's retry and add_identifier's duplicate rejection
# went on passing against a schema no deployment has.
REQUIRED_UNIQUE_CONSTRAINTS = {
    'products': {'uq_products_internal_id': ['internal_id']},
    'product_identifiers': {
        'uq_product_identifiers_type_value_scope':
            ['identifier_type', 'value', 'vendor_scope'],
    },
    'product_tags': {'uq_product_tags_product_tag': ['product_id', 'tag']},
}

# Columns whose collation the catalog's case/accent folding depends on, checked
# here against the MIGRATED schema -- the guard in test_identifier_collation.py
# only sees the create_all one, and the two are maintained independently.
FOLDING_COLUMNS = (('product_identifiers', 'value'), ('product_tags', 'tag'))


@pytest.fixture
def alembic_env(blank_database, integration_db_url, monkeypatch):
    """An Alembic config pointed at the (empty) integration database.

    ``migrations/env.py`` reads ``SQLALCHEMY_DATABASE_URI`` from the environment
    ahead of ``config.Config``/``.env``, so setting it here is what aims the
    runner at the container's random port. ``monkeypatch`` restores whatever was
    there for the rest of the session.
    """
    monkeypatch.setenv('SQLALCHEMY_DATABASE_URI', integration_db_url)
    return alembic_config()


def _structural_diffs(engine):
    """Table/column differences between the live schema and ``Base.metadata``.

    ``compare_metadata`` returns a heterogeneous list: single tuples for
    table/column-level differences and nested lists for the per-column
    modification groups. Flattened here so the filter below sees one diff per
    element.
    """
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        raw = compare_metadata(context, Base.metadata)
    flat = []
    for diff in raw:
        flat.extend(diff if isinstance(diff, list) else [diff])
    return [diff for diff in flat if diff[0] in STRUCTURAL_DIFF_KINDS]


def _table_names(engine):
    with engine.connect() as conn:
        return set(sa.inspect(conn).get_table_names())


def _column_names(engine, table):
    with engine.connect() as conn:
        return {col['name'] for col in sa.inspect(conn).get_columns(table)}


def _rows(engine, statement, **params):
    with engine.begin() as conn:
        return list(conn.execute(sa.text(statement), params))


class TestMigrationRunner:
    """The chain as a whole: it applies, it matches the models, it reverses."""

    @pytest.mark.integration
    def test_upgrade_head_succeeds_on_a_blank_database(self, alembic_env, blank_database):
        """Every revision applies, in order, to an empty MariaDB schema.

        This is the case a fresh deployment runs and the one nothing verified
        before: the unit suite never invokes Alembic at all.
        """
        command.upgrade(alembic_env, 'head')

        expected_head = ScriptDirectory.from_config(alembic_env).get_current_head()
        stamped = _rows(blank_database, 'SELECT version_num FROM alembic_version')
        assert [row[0] for row in stamped] == [expected_head]

        # Every table the models declare exists after the chain runs.
        assert set(Base.metadata.tables) <= _table_names(blank_database)

    @pytest.mark.integration
    def test_migrated_schema_matches_the_orm_metadata(self, alembic_env, blank_database):
        """The migrated schema and ``Base.metadata`` describe the same tables and
        columns.

        The two are maintained by hand and independently, so this is the check
        that catches a model column that never got a migration (production would
        error on every query) or a migration column the models forgot (dead
        schema). Only add/remove of tables and columns counts -- see
        STRUCTURAL_DIFF_KINDS for the reflection noise this deliberately
        tolerates and why.
        """
        command.upgrade(alembic_env, 'head')

        diffs = _structural_diffs(blank_database)
        assert diffs == [], (
            f'migrated schema and Base.metadata disagree about tables/columns: '
            f'{diffs}')

    @pytest.mark.integration
    def test_migrated_schema_carries_the_load_bearing_unique_constraints(
            self, alembic_env, blank_database):
        """The unique constraints the catalog service delegates its arbitration
        to exist, on the right columns, in the schema a deployment actually gets.

        ``create_product``'s retry and ``add_identifier``'s duplicate rejection
        are only correct because the database refuses the second write. Every
        other test in this tier asserts that against a ``create_all`` schema, so
        this is the only place the *migrated* schema is held to the same claim.
        """
        command.upgrade(alembic_env, 'head')

        with blank_database.connect() as conn:
            inspector = sa.inspect(conn)
            for table, expected in REQUIRED_UNIQUE_CONSTRAINTS.items():
                observed = {c['name']: list(c['column_names'])
                            for c in inspector.get_unique_constraints(table)}
                for name, columns in expected.items():
                    assert observed.get(name) == columns, (
                        f'{table}.{name} should cover {columns}, migrated '
                        f'schema has {observed.get(name)!r}')

    @pytest.mark.integration
    def test_migrated_columns_fold_case_and_accents(
            self, alembic_env, blank_database):
        """The migrated schema's folding columns are case/accent-insensitive.

        Asserted as behavior rather than by collation name: what the catalog
        depends on is that ``'A' = 'a'`` and ``'É' = 'e'`` in these columns, and
        a rename or a new default collation that preserved the behavior should
        not fail, while one that quietly stopped folding must.
        """
        command.upgrade(alembic_env, 'head')

        with blank_database.connect() as conn:
            collations = {
                (row[0], row[1]): row[2]
                for row in conn.execute(sa.text(
                    'SELECT table_name, column_name, collation_name '
                    'FROM information_schema.columns '
                    'WHERE table_schema = database() AND table_name IN :tables'
                ).bindparams(sa.bindparam(
                    'tables', [table for table, _ in FOLDING_COLUMNS],
                    expanding=True)))
            }
            for key in FOLDING_COLUMNS:
                collation = collations.get(key)
                assert collation is not None, f'{key[0]}.{key[1]} not found'
                folds = conn.execute(sa.text(
                    f"SELECT 'SHARED-1' = 'shared-1' COLLATE {collation}, "
                    f"'REF-1' = 'RÉF-1' COLLATE {collation}")).one()
                assert tuple(folds) == (1, 1), (
                    f'{key[0]}.{key[1]} uses collation {collation!r}, which '
                    f'does not fold case and accents (got {tuple(folds)}); '
                    f'every folding assumption in the catalog rests on it')

    @pytest.mark.integration
    def test_downgrade_to_base_removes_every_application_table(
            self, alembic_env, blank_database):
        """``head`` -> ``base`` leaves nothing behind but Alembic's own bookkeeping.

        A downgrade that raises halfway is the failure mode that matters here:
        it strands a production database in a state no revision describes. Only
        ``alembic_version`` may survive -- Alembic owns that table and does not
        drop it -- and it must be left holding no revision at all, since a
        surviving stamp would make the next ``upgrade head`` skip every revision
        below it and rebuild a partial schema.
        """
        command.upgrade(alembic_env, 'head')
        command.downgrade(alembic_env, 'base')

        assert _table_names(blank_database) - {'alembic_version'} == set()
        assert _rows(blank_database, 'SELECT version_num FROM alembic_version') == []


class TestInternalIdBackfill:
    """Story 2.4's data migration (5aeb89e22451) against the real backend.

    The backfill is one of two migrations in the tree that read and write rows
    rather than only issuing DDL (the other is
    f8e66632ee42_normalize_existing_category_paths, which the runner above
    applies but only ever against an empty ``products`` table), and its
    correctness claims -- distinct generated ids, adoption of a pre-existing
    canonical row instead of writing a second disagreeing one, and leaving
    vendor-scoped rows alone -- are all claims about data the SQLite suite never
    puts in front of it.
    """

    @pytest.fixture
    def backfilled(self, alembic_env, blank_database):
        """The I/O matrix's three products, migrated across 5aeb89e22451.

        * P1 carries no identifier rows at all (the generate branch).
        * P2 carries one canonical global INTERNAL row (the adopt branch).
        * P3 carries a vendor-scoped INTERNAL row only (neither branch -- it
          generates, and the scoped row must survive untouched).

        Yields their ids in that order.
        """
        # The two revisions are hard-coded, so state the relationship the whole
        # class assumes. If a revision is ever inserted between them, this fails
        # naming the constants to update rather than silently exercising a
        # different chain (or dying in an opaque Alembic KeyError).
        script = ScriptDirectory.from_config(alembic_env)
        assert script.get_revision(INTERNAL_ID_REVISION).down_revision == \
            BEFORE_INTERNAL_ID, (
                f'{INTERNAL_ID_REVISION} no longer follows {BEFORE_INTERNAL_ID} '
                f'directly; update the constants in this module')

        command.upgrade(alembic_env, BEFORE_INTERNAL_ID)

        with blank_database.begin() as conn:
            ids = []
            for description in ('P1', 'P2', 'P3'):
                result = conn.execute(sa.text(
                    'INSERT INTO products (description, created_at, updated_at) '
                    'VALUES (:d, NOW(), NOW())'), {'d': description})
                ids.append(result.lastrowid)
            p1, p2, p3 = ids

            conn.execute(sa.text(
                'INSERT INTO product_identifiers '
                '(product_id, identifier_type, value, vendor_scope, created_at) '
                "VALUES (:pid, 'INTERNAL', :value, '', NOW())"),
                {'pid': p2, 'value': ADOPTED_INTERNAL_ID})
            conn.execute(sa.text(
                'INSERT INTO product_identifiers '
                '(product_id, identifier_type, value, vendor_scope, created_at) '
                "VALUES (:pid, 'INTERNAL', :value, :scope, NOW())"),
                {'pid': p3, 'value': VENDOR_SCOPED_VALUE, 'scope': VENDOR_SCOPE})

        command.upgrade(alembic_env, INTERNAL_ID_REVISION)
        return p1, p2, p3

    @staticmethod
    def _internal_ids(engine):
        return dict(_rows(engine, 'SELECT id, internal_id FROM products'))

    @staticmethod
    def _global_internal_rows(engine, product_id):
        return [row[0] for row in _rows(
            engine,
            'SELECT value FROM product_identifiers WHERE product_id = :pid '
            "AND identifier_type = 'INTERNAL' AND vendor_scope = ''",
            pid=product_id)]

    @pytest.mark.integration
    def test_every_product_gets_a_distinct_canonical_internal_id(
            self, backfilled, blank_database):
        """No pre-existing row blocks the upgrade, and the values the backfill
        writes are the same shape ``create_product`` issues at runtime -- the
        migration imports the very same generator to guarantee it."""
        internal_ids = self._internal_ids(blank_database)

        assert set(internal_ids) == set(backfilled)
        assert all(is_valid_internal_id(value) for value in internal_ids.values())
        assert len(set(internal_ids.values())) == len(backfilled)

    @pytest.mark.integration
    def test_product_with_a_canonical_row_adopts_it_without_gaining_a_second(
            self, backfilled, blank_database):
        """P2 takes its existing row's value as its internal_id.

        Writing a fresh value instead would leave the derived index permanently
        disagreeing with the column it mirrors -- the exact condition the
        column's UNIQUE constraint exists to make impossible.
        """
        _, p2, _ = backfilled

        assert self._internal_ids(blank_database)[p2] == ADOPTED_INTERNAL_ID
        assert self._global_internal_rows(blank_database, p2) == [ADOPTED_INTERNAL_ID]

    @pytest.mark.integration
    def test_products_without_one_gain_exactly_one_derived_row(
            self, backfilled, blank_database):
        """P1 and P3 each get one global INTERNAL row equal to their new column."""
        p1, _, p3 = backfilled
        internal_ids = self._internal_ids(blank_database)

        for product_id in (p1, p3):
            assert self._global_internal_rows(blank_database, product_id) == \
                   [internal_ids[product_id]]

    @pytest.mark.integration
    def test_vendor_scoped_internal_row_is_left_alone(self, backfilled, blank_database):
        """P3's vendor-scoped row is neither adopted nor removed.

        It lives outside the global (type, value, scope) namespace, so treating
        it as the derived index would both break the global-scope invariant and
        hide a genuine integrity error behind a fabricated collision later.
        """
        _, _, p3 = backfilled

        scoped = _rows(
            blank_database,
            'SELECT value, vendor_scope FROM product_identifiers '
            "WHERE product_id = :pid AND identifier_type = 'INTERNAL' "
            "AND vendor_scope <> ''", pid=p3)
        assert [tuple(row) for row in scoped] == [(VENDOR_SCOPED_VALUE, VENDOR_SCOPE)]
        assert self._internal_ids(blank_database)[p3] != VENDOR_SCOPED_VALUE

    @pytest.mark.integration
    def test_downgrade_reverses_the_backfill(
            self, backfilled, alembic_env, blank_database):
        """Back at 3beb9dff5e41: the column, its constraint, and every derived
        row are gone -- including the one that was adopted, which by then is
        indistinguishable from one the migration inserted -- while the
        vendor-scoped row survives."""
        _, _, p3 = backfilled

        command.downgrade(alembic_env, BEFORE_INTERNAL_ID)

        assert 'internal_id' not in _column_names(blank_database, 'products')
        with blank_database.connect() as conn:
            constraints = sa.inspect(conn).get_unique_constraints('products')
        assert 'uq_products_internal_id' not in {c['name'] for c in constraints}

        # Every derived/adopted global INTERNAL row is gone...
        assert _rows(blank_database,
                     'SELECT id FROM product_identifiers '
                     "WHERE identifier_type = 'INTERNAL' AND vendor_scope = ''") == []
        # ...and P3's vendor-scoped row is untouched.
        assert [tuple(row) for row in _rows(
            blank_database,
            'SELECT product_id, value, vendor_scope FROM product_identifiers')] == \
            [(p3, VENDOR_SCOPED_VALUE, VENDOR_SCOPE)]
