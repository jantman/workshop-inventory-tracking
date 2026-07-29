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
from tests.integration.conftest import (ALEMBIC_TABLE, BINARY_COLLATION,
                                        CONTRAST_COLLATION,
                                        NON_FOLDING_COLLATION,
                                        REQUIRED_CHARSET, REQUIRED_COLLATION,
                                        alembic_config,
                                        assert_schema_is_pinned,
                                        column_collations, database_default,
                                        table_collations)

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

# The revision that pins an explicit charset and per-column collation, and the
# one before it (DW-34). Hard-coded like the Story 2.4 pair above, and checked
# against the script directory before use.
COLLATION_REVISION = 'a977ca7315df'
BEFORE_COLLATION = '68707d1f48bf'

# Two internal ids differing only in case. Distinct under utf8mb4_bin, one value
# under any _ci collation -- so inserting both is the direct test of which one
# uq_products_internal_id is arbitrating with.
INTERNAL_ID_UPPER = 'ABC1234567'
INTERNAL_ID_LOWER = 'abc1234567'

# A tag pair that is distinct under a binary collation and collides under
# utf8mb4_unicode_ci, which folds accents as well as case. Seeded before the
# collation revision to trigger its pre-flight abort.
TAG_UNACCENTED = 'cafe'
TAG_ACCENTED = 'café'

# A database default NARROWER than utf8mb4, for the one refusal keyed on the
# charset rather than on the collation: `downgrade()` converts every table back
# to the database default, and doing that to latin1 would replace every
# unrepresentable character in the stored text with '?'. Kept distinct from
# CONTRAST_COLLATION, which is a utf8mb4 collation and cannot exercise it.
NARROW_CHARSET = 'latin1'
NARROW_COLLATION = 'latin1_swedish_ci'

# The shape `MODIFY internal_id VARCHAR(32) NOT NULL COLLATE ...` restates. The
# drift check above discards 'modify_type' and 'modify_nullable' to suppress
# reflection noise, and assert_schema_is_pinned compares collations only, so
# without this a MODIFY that narrowed the column or dropped its NOT NULL would
# pass the whole tier.
INTERNAL_ID_COLUMN_TYPE = 'varchar(32)'


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


class TestPinnedCollations:
    """DW-34's revision: the schema states its own charset and collation.

    Every other collation assertion in this file observes only what the columns
    INHERITED from ``integration_db_url``'s ``ALTER DATABASE``. That was the
    honest limit of the old guard and the reason DW-51 stayed open: a fixture
    that forces the database default cannot tell a schema that pins the
    collation apart from one that merely happens to be created inside a database
    with the right default, and a *deployment* gets no such fixture. The tests
    below close that by making the inherited value differ from the target on
    purpose (test_identifier_collation.py does the same for the ``create_all``
    schema, which is built and maintained independently of this chain).
    """

    @pytest.fixture(autouse=True)
    def _revision_chain_is_what_this_class_assumes(self, alembic_env):
        """Fail naming the constants to update if the chain is reordered.

        Same guard, and same reason, as ``TestInternalIdBackfill.backfilled``:
        a revision inserted between these two would otherwise turn the
        pre-flight test into an opaque Alembic error or, worse, a silent test
        of a different migration.
        """
        script = ScriptDirectory.from_config(alembic_env)
        assert script.get_revision(COLLATION_REVISION).down_revision == \
            BEFORE_COLLATION, (
                f'{COLLATION_REVISION} no longer follows {BEFORE_COLLATION} '
                f'directly; update the constants in this module')

    @pytest.mark.integration
    def test_migrated_schema_pins_the_charset_and_collation(
            self, alembic_env, blank_database):
        """Every table defaults to utf8mb4/utf8mb4_unicode_ci and every string
        column reports that collation -- except the ``BINARY_COLUMNS``
        (``products.internal_id`` and ``products.stock_status``), which report
        utf8mb4_bin."""
        command.upgrade(alembic_env, 'head')

        assert_schema_is_pinned(blank_database)

        # Keyed by (table, column), not by table: the query returns one row per
        # COLUMN, so collapsing it onto table_name would keep whichever column
        # came last and let a single unconverted column pass unseen.
        # ``alembic_version`` is excluded for the reason conftest states -- it
        # is Alembic's table, created on its own terms, and asserting its
        # charset would make this test depend on the very database default it
        # exists to prove the schema does not depend on.
        wrong_charset = {(row[0], row[1]): row[2] for row in _rows(
            blank_database,
            'SELECT table_name, column_name, character_set_name '
            'FROM information_schema.columns '
            'WHERE table_schema = database() '
            'AND character_set_name IS NOT NULL '
            'AND character_set_name <> :charset '
            'AND table_name <> :alembic', charset=REQUIRED_CHARSET,
            alembic=ALEMBIC_TABLE)}
        assert wrong_charset == {}, (
            f'columns on a character set other than {REQUIRED_CHARSET} survive '
            f'the migration: {wrong_charset}')

        # The binary pin is applied by a `MODIFY`, and MySQL's MODIFY REPLACES
        # a column definition rather than patching it -- so the statement has
        # to restate `VARCHAR(32) NOT NULL`, and getting that restatement wrong
        # is invisible to every other check here: `_structural_diffs` discards
        # 'modify_type' and 'modify_nullable', and `assert_schema_is_pinned`
        # compares collations. A narrowed column would silently truncate every
        # id it stores.
        column_type, is_nullable = _rows(
            blank_database,
            'SELECT column_type, is_nullable '
            'FROM information_schema.columns WHERE table_schema = database() '
            "AND table_name = 'products' AND column_name = 'internal_id'")[0]
        assert (column_type.lower(), is_nullable) == \
            (INTERNAL_ID_COLUMN_TYPE, 'NO'), (
                f'the MODIFY that pins internal_id binary also redefined it as '
                f'{column_type} nullable={is_nullable}; it is meant to restate '
                f'{INTERNAL_ID_COLUMN_TYPE} NOT NULL unchanged')

    @pytest.mark.integration
    def test_pinning_beats_a_contrary_database_default(
            self, alembic_env, blank_database):
        """The chain applied inside a database whose default is
        ``CONTRAST_COLLATION`` still produces the pinned collations.

        This is the test the pinning exists for, and the one that could not be
        written before it: with the database default set to the target, every
        assertion above passes just as well against a schema that declares
        nothing at all. Here the inherited value is deliberately WRONG -- and
        wrong for BOTH pins, folding and binary, which is why the contrast is a
        third collation rather than one of the two. Only a schema that states
        its own collation can pass. The default is restored unconditionally --
        the database is session-scoped and shared with every other test in the
        tier.

        This is also, incidentally, the tier's only guard on revisions added
        AFTER the pinning one, and that is worth stating rather than relying on:
        `alembic revision --autogenerate` never decorates an `op.create_table()`
        with mysql_charset/mysql_collate, and the revision under test pins the
        nine tables that existed when it was written rather than the database
        default. A table introduced by a later revision therefore inherits
        `@@collation_database` again -- and because this test upgrades to
        `head` rather than to COLLATION_REVISION, and does so inside a database
        whose default is deliberately wrong, that table fails here.
        """
        with database_default(blank_database, CONTRAST_COLLATION):
            command.upgrade(alembic_env, 'head')

            assert_schema_is_pinned(blank_database)

    @pytest.mark.integration
    def test_migrated_internal_id_is_case_sensitive_while_tags_fold(
            self, alembic_env, blank_database):
        """Two internal ids differing only in case coexist; two tags differing
        only in case do not.

        The pair asserted together, because the value of the binary pin is
        precisely that it differs from the schema-wide default: a run that
        proved only the first would also pass on a schema where NOTHING folds,
        which is the deployment DW-34 exists to make impossible.
        """
        command.upgrade(alembic_env, 'head')

        with blank_database.begin() as conn:
            for value in (INTERNAL_ID_UPPER, INTERNAL_ID_LOWER):
                conn.execute(sa.text(
                    'INSERT INTO products (internal_id, created_at, updated_at) '
                    'VALUES (:v, NOW(), NOW())'), {'v': value})

        stored = {row[0] for row in _rows(
            blank_database, 'SELECT internal_id FROM products')}
        assert stored == {INTERNAL_ID_UPPER, INTERNAL_ID_LOWER}, (
            'uq_products_internal_id folded two ids that differ only in case; '
            'products.internal_id is meant to be utf8mb4_bin')

        # ...and the exact-equality lookup resolve_scan performs agrees with
        # is_valid_internal_id rather than with the folding default (DW-73).
        assert [row[0] for row in _rows(
            blank_database,
            'SELECT internal_id FROM products WHERE internal_id = :v',
            v=INTERNAL_ID_LOWER)] == [INTERNAL_ID_LOWER]

        product_id = _rows(blank_database,
                           'SELECT id FROM products LIMIT 1')[0][0]
        with blank_database.begin() as conn:
            conn.execute(sa.text(
                'INSERT INTO product_tags (product_id, tag, created_at) '
                'VALUES (:pid, :tag, NOW())'),
                {'pid': product_id, 'tag': TAG_UNACCENTED})
        with pytest.raises(sa.exc.IntegrityError):
            with blank_database.begin() as conn:
                conn.execute(sa.text(
                    'INSERT INTO product_tags (product_id, tag, created_at) '
                    'VALUES (:pid, :tag, NOW())'),
                    {'pid': product_id, 'tag': TAG_ACCENTED})

    @pytest.mark.integration
    def test_preflight_aborts_before_any_ddl_on_a_pre_existing_collision(
            self, alembic_env, blank_database):
        """Rows that fold together under the target stop the migration dead.

        MySQL commits DDL implicitly, so an ``ALTER TABLE`` that failed partway
        down the list would strand a half-converted schema no revision
        describes. The migration's pre-flight check exists to turn that into an
        actionable abort with nothing changed, and 'nothing changed' is what the
        second half of this test asserts -- the whole schema, not just
        ``product_tags``, is still on the contrasting collation afterwards.

        The seeding needs a NON-FOLDING default, not merely a contrasting one:
        under ``utf8mb4_unicode_ci`` -- or under ``CONTRAST_COLLATION``, which
        folds Latin-1 accents just the same -- the two tags could not have been
        inserted in the first place, which is the point.
        """
        with database_default(blank_database, NON_FOLDING_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)

            with blank_database.begin() as conn:
                product_id = conn.execute(sa.text(
                    'INSERT INTO products (internal_id, created_at, updated_at) '
                    'VALUES (:v, NOW(), NOW())'),
                    {'v': INTERNAL_ID_UPPER}).lastrowid
                for tag in (TAG_UNACCENTED, TAG_ACCENTED):
                    conn.execute(sa.text(
                        'INSERT INTO product_tags (product_id, tag, created_at) '
                        'VALUES (:pid, :tag, NOW())'),
                        {'pid': product_id, 'tag': tag})

            with pytest.raises(RuntimeError) as exc_info:
                command.upgrade(alembic_env, COLLATION_REVISION)

            message = str(exc_info.value)
            assert 'product_tags' in message
            assert 'uq_product_tags_product_tag' in message
            assert TAG_ACCENTED in message and TAG_UNACCENTED in message

            # No DDL was issued: every table still carries the collation it
            # inherited, and the revision was not stamped.
            collations = set(table_collations(blank_database).values())
            assert collations == {NON_FOLDING_COLLATION}, (
                f'the aborted migration converted something: {collations}')
            assert [row[0] for row in _rows(
                blank_database, 'SELECT version_num FROM alembic_version')] == \
                [BEFORE_COLLATION]

    @pytest.mark.integration
    def test_rows_with_a_null_unique_key_are_not_a_collision(
            self, alembic_env, blank_database):
        """Many purchases with no ``request_key`` do not stop the upgrade.

        MySQL allows unlimited NULLs in a UNIQUE index, so rows with a NULL
        anywhere in the key are exempt from uniqueness and can neither collide
        nor be reported as colliding. The pre-flight has to exclude them by
        hand, and getting that wrong is not a subtle failure: ``request_key`` is
        only written by Epic 7's idempotency path, which has not landed, so
        almost every purchase in a real database leaves it NULL. A check that
        grouped them would abort the upgrade on essentially every deployment
        while every test that seeds no purchases -- which is all of the others
        -- went on passing.
        """
        with database_default(blank_database, CONTRAST_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)

            with blank_database.begin() as conn:
                product_id = conn.execute(sa.text(
                    'INSERT INTO products (internal_id, created_at, updated_at) '
                    'VALUES (:v, NOW(), NOW())'),
                    {'v': INTERNAL_ID_UPPER}).lastrowid
                for _ in range(3):
                    conn.execute(sa.text(
                        'INSERT INTO purchases '
                        '(product_id, request_key, created_at, updated_at) '
                        'VALUES (:pid, NULL, NOW(), NOW())'),
                        {'pid': product_id})

            command.upgrade(alembic_env, COLLATION_REVISION)
            # ...and then on to head, because `assert_schema_is_pinned` compares
            # the observed columns against `Base.metadata`, which describes the
            # END of the chain. Stopping at COLLATION_REVISION was equivalent
            # only while that revision happened to be head; the first additive
            # revision after it (2c837402a89a) made a halted schema legitimately
            # disagree with the models. The claim under test is unaffected —
            # what matters is that the pre-flight let the upgrade through with
            # those NULL request_keys in place, and it has by the line above.
            # Continuing inside the contrary default is worth something extra:
            # ADD COLUMN inherits the TABLE's charset/collation, so the new
            # columns must come out pinned rather than picking the database
            # default back up.
            command.upgrade(alembic_env, 'head')

            assert_schema_is_pinned(blank_database)

    @pytest.mark.integration
    def test_preflight_catches_an_internal_id_collision(
            self, alembic_env, blank_database):
        """The transient the migration's docstring devotes a paragraph to.

        ``products.internal_id`` ends up ``utf8mb4_bin``, which only LOOSENS
        uniqueness, so it looks like it needs no pre-flight. It does: the
        table-wide ``CONVERT TO`` runs first and puts the column under the
        folding collation, and the ``MODIFY`` that pins it binary runs after --
        so two ids differing only in case fail the conversion, five tables into
        the list. Asserted rather than argued, because the argument is subtle
        enough that a future reordering could quietly invalidate it.
        """
        with database_default(blank_database, NON_FOLDING_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)

            with blank_database.begin() as conn:
                for value in (INTERNAL_ID_UPPER, INTERNAL_ID_LOWER):
                    conn.execute(sa.text(
                        'INSERT INTO products '
                        '(internal_id, created_at, updated_at) '
                        'VALUES (:v, NOW(), NOW())'), {'v': value})

            with pytest.raises(RuntimeError) as exc_info:
                command.upgrade(alembic_env, COLLATION_REVISION)

            message = str(exc_info.value)
            assert 'uq_products_internal_id' in message
            assert INTERNAL_ID_UPPER in message and INTERNAL_ID_LOWER in message
            assert set(table_collations(blank_database).values()) == \
                {NON_FOLDING_COLLATION}

    @pytest.mark.integration
    def test_preflight_compares_only_a_prefix_indexs_prefix(
            self, alembic_env, blank_database):
        """A prefix index is checked on its prefix, not on the whole column.

        ``information_schema.statistics.sub_part`` is the only reason
        ``_unique_indexes`` emits ``LEFT(...)``, and no index in the models is a
        prefix one -- so without a test the branch that stops the check
        UNDER-reporting is dead code. A deployed schema is free to have one,
        which is the whole reason the pre-flight discovers indexes instead of
        listing them.

        The two values are equal in their first five characters after folding
        and differ afterwards: a check grouping the FULL column would see two
        distinct keys and let the migration through to a duplicate-key failure
        mid-conversion.
        """
        with database_default(blank_database, NON_FOLDING_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)

            with blank_database.begin() as conn:
                conn.execute(sa.text(
                    'CREATE UNIQUE INDEX ux_products_mpn_prefix '
                    'ON products (mpn(5))'))
                # The internal ids are unrelated and plainly distinct, so the
                # only index that can fire is the prefix one.
                for internal_id, mpn in (('AAAA111111', 'cafe-1'),
                                         ('BBBB222222', 'café-2')):
                    conn.execute(sa.text(
                        'INSERT INTO products '
                        '(internal_id, mpn, created_at, updated_at) '
                        'VALUES (:v, :mpn, NOW(), NOW())'),
                        {'v': internal_id, 'mpn': mpn})

            with pytest.raises(RuntimeError) as exc_info:
                command.upgrade(alembic_env, COLLATION_REVISION)

            assert 'ux_products_mpn_prefix' in str(exc_info.value)
            assert set(table_collations(blank_database).values()) == \
                {NON_FOLDING_COLLATION}

    @pytest.mark.integration
    def test_upgrade_refuses_a_schema_that_is_not_already_utf8mb4(
            self, alembic_env, blank_database):
        """Converting a narrower charset would be a WIDENING, so it is refused.

        Three consequences the migration cannot undo, all documented in its
        docstring: index keys grow past the 767-byte limit of the row formats a
        deployment this vintage is likely to use, ``TEXT`` is silently promoted
        to ``MEDIUMTEXT`` so the migrated schema stops matching ``create_all``,
        and ``downgrade()`` -- which refuses to convert back to a narrower
        default -- becomes unreachable. Only one table is moved here because the
        check has to fail on ANY of them, not just on a uniformly-latin1 schema.
        """
        command.upgrade(alembic_env, BEFORE_COLLATION)
        with blank_database.begin() as conn:
            conn.execute(sa.text(
                'ALTER TABLE `product_tags` CONVERT TO CHARACTER SET latin1'))

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(alembic_env, COLLATION_REVISION)

        message = str(exc_info.value)
        assert 'product_tags' in message and 'latin1' in message
        assert [row[0] for row in _rows(
            blank_database, 'SELECT version_num FROM alembic_version')] == \
            [BEFORE_COLLATION]

    @pytest.mark.integration
    def test_upgrade_refuses_when_a_table_is_missing(
            self, alembic_env, blank_database):
        """A dropped table is a refusal, not an ERROR 1146 six tables in.

        ``TABLES`` in the migration is a fixed list and the schema it converts
        is a deployed one, so the two can disagree. The conversion loop would
        otherwise commit every table before the missing one and then die.

        Run inside ``CONTRAST_COLLATION`` for the reason the refusal exists: at
        the tier's normal default the surviving tables are already on the target
        collation, so a check that ran AFTER the conversion loop instead of
        before it would leave a schema indistinguishable from an untouched one
        and this test could not tell the difference. With a contrary default,
        "nothing was converted" is observable.
        """
        with database_default(blank_database, CONTRAST_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)
            with blank_database.begin() as conn:
                conn.execute(sa.text('SET FOREIGN_KEY_CHECKS = 0'))
                conn.execute(sa.text('DROP TABLE `product_tags`'))
                conn.execute(sa.text('SET FOREIGN_KEY_CHECKS = 1'))

            with pytest.raises(RuntimeError) as exc_info:
                command.upgrade(alembic_env, COLLATION_REVISION)

            assert 'product_tags' in str(exc_info.value)
            assert set(table_collations(blank_database).values()) == \
                {CONTRAST_COLLATION}
            assert [row[0] for row in _rows(
                blank_database,
                'SELECT version_num FROM alembic_version')] == \
                [BEFORE_COLLATION]

    @pytest.mark.integration
    def test_preflight_handles_an_index_mixing_a_string_and_a_binary_column(
            self, alembic_env, blank_database):
        """A UNIQUE index over a VARCHAR and a BLOB prefix is checked, not fatal.

        Two branches meet here and neither is reachable from the models, which
        is precisely why a deployed schema is what the pre-flight discovers
        rather than what it assumes:

        * the ``collatable`` flag. Appending ``COLLATE utf8mb4_unicode_ci`` to a
          binary-charset column is `ERROR 1253`, not a no-op, so a key mixing
          the two would crash the check instead of reporting through it.
        * the ``sub_part`` prefix on that binary member. Grouping on the whole
          BLOB instead of its first N bytes would UNDER-report -- and the values
          below are byte-identical over the prefix and differ afterwards, so a
          check that missed it would pass and hand the conversion a
          duplicate-key failure mid-loop.

        The reported sample comes back as `bytes` rather than `str` for the same
        reason (CONCAT_WS over a binary argument is binary), which is the third
        thing asserted: the abort must be the actionable RuntimeError, not an
        AttributeError from the code that formats it.
        """
        payload = b'0123456789abcdef'
        with database_default(blank_database, NON_FOLDING_COLLATION):
            command.upgrade(alembic_env, BEFORE_COLLATION)

            with blank_database.begin() as conn:
                conn.execute(sa.text(
                    'CREATE UNIQUE INDEX ux_photos_filename_thumb '
                    'ON photos (filename, thumbnail_data(16))'))
                for filename, suffix in ((TAG_UNACCENTED, b'-one'),
                                         (TAG_ACCENTED, b'-two')):
                    conn.execute(sa.text(
                        'INSERT INTO photos (filename, content_type, '
                        'file_size, thumbnail_data, medium_data, '
                        'original_data, created_at, updated_at) '
                        "VALUES (:name, 'image/jpeg', 1, :thumb, :thumb, "
                        ':thumb, NOW(), NOW())'),
                        {'name': f'{filename}.jpg',
                         'thumb': payload + suffix})

            with pytest.raises(RuntimeError) as exc_info:
                command.upgrade(alembic_env, COLLATION_REVISION)

            assert 'ux_photos_filename_thumb' in str(exc_info.value)
            assert set(table_collations(blank_database).values()) == \
                {NON_FOLDING_COLLATION}

    @pytest.mark.integration
    def test_downgrade_refuses_a_narrower_database_default(
            self, alembic_env, blank_database):
        """Reversing into a latin1 default would silently mangle stored text.

        ``downgrade()`` converts every table to whatever the database default
        is, so a narrower default turns the reversal into a lossy transcoding:
        every character the target charset cannot represent becomes '?', with no
        way back. The refusal is the only branch in either direction keyed on
        the database CHARSET rather than on a collation, and until
        ``database_default`` could vary the charset nothing could reach it --
        so an inverted comparison here would have shipped green.
        """
        # Stopped AT the revision under test rather than run on to head: this
        # exercises that revision's own downgrade branch, and reaching it from
        # head would first run every later revision's downgrade — 2c837402a89a
        # drops four columns and succeeds — so "nothing was changed" would no
        # longer be true of the schema by the time the refusal fired.
        command.upgrade(alembic_env, COLLATION_REVISION)

        # Snapshotted rather than compared against `Base.metadata`, which
        # describes head and therefore carries columns a schema halted here has
        # never had. A before/after comparison is also the stronger statement of
        # the claim: "refused before any DDL" is exactly "the schema is the one
        # we walked in with", whatever revision that happens to be. The two
        # value assertions keep it from being vacuous — an equal pair of BROKEN
        # snapshots would otherwise pass.
        pinned_tables = table_collations(blank_database)
        pinned_columns = column_collations(blank_database)
        assert set(pinned_tables.values()) == {REQUIRED_COLLATION}
        assert set(pinned_columns.values()) == {REQUIRED_COLLATION,
                                                BINARY_COLLATION}

        with database_default(blank_database, NARROW_COLLATION,
                              charset=NARROW_CHARSET):
            with pytest.raises(RuntimeError) as exc_info:
                command.downgrade(alembic_env, BEFORE_COLLATION)

            assert NARROW_CHARSET in str(exc_info.value)
            # Refused before any DDL: the schema still carries the pins.
            assert table_collations(blank_database) == pinned_tables
            assert column_collations(blank_database) == pinned_columns
            assert [row[0] for row in _rows(
                blank_database,
                'SELECT version_num FROM alembic_version')] == \
                [COLLATION_REVISION]

    @pytest.mark.integration
    def test_downgrade_restores_the_database_default(
            self, alembic_env, blank_database):
        """Reversing the revision hands every table back to the DB default.

        The tier's other downgrade test runs with the database default already
        at the target, so its ``CONVERT TO`` is a no-op and proves nothing about
        the reversal. Here the default differs from both pins, so the tables
        must actually move -- and ``products.internal_id``, whose binary pin is
        per-column DDL rather than a table default, has to give it up along with
        everything else.
        """
        with database_default(blank_database, CONTRAST_COLLATION):
            # Run to head, not merely to COLLATION_REVISION: `assert_schema_is_
            # pinned` measures against `Base.metadata`, which describes the end
            # of the chain, and the later additive revisions' columns have to be
            # in place for that comparison to mean anything. The downgrade below
            # still crosses the revision under test — it just crosses the ones
            # after it first, which drop their own columns and are no-ops for
            # every collation this test reads.
            command.upgrade(alembic_env, 'head')
            assert_schema_is_pinned(blank_database)

            command.downgrade(alembic_env, BEFORE_COLLATION)

            assert set(table_collations(blank_database).values()) == \
                {CONTRAST_COLLATION}
            internal_id = _rows(
                blank_database,
                'SELECT collation_name FROM information_schema.columns '
                "WHERE table_schema = database() AND table_name = 'products' "
                "AND column_name = 'internal_id'")[0][0]
            assert internal_id == CONTRAST_COLLATION, (
                'the binary pin survived the downgrade; CONVERT TO CHARACTER '
                'SET is supposed to override the per-column collation too')


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
