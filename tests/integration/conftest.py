"""
Fixtures for the MariaDB integration tier.

Everything under ``tests/integration/`` runs against a *real* MariaDB server:
locally the session-scoped ``mariadb_testcontainer`` fixture (tests/test_database.py)
starts ``mariadb:11.8``, under ``CI=true`` it yields None and the workflow's
service container is already listening. This module owns the three things that
differ from the SQLite unit tier -- URL resolution, per-test isolation, and
Alembic wiring -- so no individual test file has to reinvent them.

Why these tests exist at all: three mechanisms in this codebase are only
*staged* under SQLite and genuinely arbitrated by InnoDB in production -- the
Alembic upgrade/downgrade pair, ``create_product``'s let-the-UNIQUE-constraint-
arbitrate retry, and ``add_identifier``'s duplicate rejection under a
case/accent-folding collation. The unit suite is actively *looser* than
production about the last of those, so a green unit run proves less than it
looks like it does.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

from app.database import Base
from app.mariadb_catalog_service import CatalogService
from app.mariadb_inventory_service import InventoryService
from app.mariadb_storage import MariaDBStorage
from config import TestConfig

# tests/integration/conftest.py -> tests/integration -> tests -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# The collation every folding assumption in the catalog subsystem rests on.
# PINNED by the schema itself since DW-34 -- `app/database.py`'s
# MYSQL_TABLE_OPTIONS for the create_all schema, migration a977ca7315df for a
# migrated one -- and additionally forced at the database level by
# `integration_db_url` below, which since the pinning serves as a contrast
# baseline rather than as the thing setting the collation. Asserted by
# tests/integration/test_identifier_collation.py (create_all schema) and
# tests/integration/test_migrations.py (migrated schema).
REQUIRED_COLLATION = 'utf8mb4_unicode_ci'
REQUIRED_CHARSET = 'utf8mb4'

# The one column deliberately NOT folded: products.internal_id is a case-stable
# generated identifier whose validator (`is_valid_internal_id`) is
# case-sensitive by design, so a folding collation there would make MariaDB
# disagree with both that validator and SQLite (DW-73).
BINARY_COLLATION = 'utf8mb4_bin'
BINARY_COLUMNS = {('products', 'internal_id')}

# A database default collation deliberately DIFFERENT from EVERY pinned value,
# for the tests that build a schema inside `database_default(...)` and then
# assert the schema pinned its own. It has to differ from the binary pin as well
# as from the folding one: with utf8mb4_bin as the contrast, "products
# .internal_id is utf8mb4_bin" would be satisfied identically by the pin and by
# plain inheritance, leaving the one column whose pin is most behaviorally
# load-bearing (DW-73) the one the contrast tests could not actually prove.
# utf8mb4_general_ci is a legal default a deployment could genuinely have and
# equals neither pin.
CONTRAST_COLLATION = 'utf8mb4_general_ci'

# The contrast for tests that must SEED rows the target collation will fold --
# a pre-existing collision, which is only insertable while the schema does not
# yet fold it. CONTRAST_COLLATION is no good for that: utf8mb4_general_ci folds
# accents in the Latin-1 range just as utf8mb4_unicode_ci does, so 'cafe' and
# 'café' collide there too and the seeding fails before the test begins.
# utf8mb4_bin folds nothing, which is exactly what seeding needs. The two
# contrasts are separate constants rather than one compromise because no single
# collation can both differ from every pin AND fold nothing.
NON_FOLDING_COLLATION = BINARY_COLLATION

# The naming rule a database must satisfy before this tier is willing to destroy
# it: a '_test' suffix, or the bare name 'test'. A 'test' SUBSTRING would also
# accept 'latest_inventory' and 'contest_results', and a bare 'test' SUFFIX would
# accept 'latest' -- requiring the separator costs nothing (both the container
# and the CI service container use 'workshop_inventory_test') and drops that
# whole class of near-miss. See _assert_safe_target for why a guard is not
# paranoia here.
TEST_DATABASE_SUFFIX = '_test'
TEST_DATABASE_EXACT = 'test'


def pytest_collection_modifyitems(items):
    """Mark everything under ``tests/integration/`` as ``integration``.

    The tier is scoped by marker expression, not by path: ``nox -s integration``
    selects ``-m integration`` and both ``tests`` and ``coverage`` deselect it.
    A test that forgot the decorator would therefore vanish from its own session
    AND be collected by the unit session -- which runs under ``--blockage`` with
    no database, so it would fail there for an unrelated-looking reason. Applying
    the marker structurally makes that impossible; the explicit decorators on
    each test stay for readability.

    ``here`` is resolved because ``item.path`` is: a checkout reached through a
    symlink would otherwise compare an unresolved prefix against resolved item
    paths, match nothing, and silently void the guarantee this hook exists for.
    """
    here = Path(__file__).resolve().parent
    for item in items:
        try:
            path = Path(item.path).resolve()
        except (AttributeError, TypeError, OSError):  # pragma: no cover - defensive
            continue
        if here in path.parents:
            item.add_marker(pytest.mark.integration)


def _assert_safe_target(url: str) -> sa.engine.url.URL:
    """Refuse to run unless the URL names a MariaDB *test* database.

    The fixtures below drop every table in the target and `ALTER DATABASE` it.
    Nothing else guarantees the target is disposable: ``config.py`` calls
    ``load_dotenv()`` at import, so a developer's real ``SQLALCHEMY_DATABASE_URI``
    is already in the environment by the time these fixtures run, and it is only
    displaced because ``mariadb_testcontainer`` overwrites it -- which that
    fixture skips entirely when ``CI`` is set. A stray ``CI=true`` in a local
    shell is all it takes, and the failure mode is an erased inventory database.
    """
    parsed = sa.make_url(url)
    if not parsed.get_backend_name().startswith('mysql'):
        pytest.fail(
            f'the integration tier requires MariaDB, got backend '
            f'{parsed.get_backend_name()!r} from {parsed.render_as_string()!r}')
    if not parsed.database:
        pytest.fail(
            f'the resolved database URL names no database: '
            f'{parsed.render_as_string()!r}')
    name = parsed.database.lower()
    if not (name.endswith(TEST_DATABASE_SUFFIX) or name == TEST_DATABASE_EXACT):
        pytest.fail(
            f'refusing to drop every table in database {parsed.database!r}: '
            f'the integration tier only runs against a database named '
            f'{TEST_DATABASE_EXACT!r} or ending in {TEST_DATABASE_SUFFIX!r}. '
            f'Check SQLALCHEMY_DATABASE_URI and TEST_DB_NAME.')
    return parsed


def alembic_config() -> AlembicConfig:
    """An Alembic ``Config`` built in-process, with no ``alembic.ini``.

    Two deliberate properties:

    * ``script_location`` is an ABSOLUTE path, so the migration runner does not
      depend on pytest's cwd.
    * No config *file* is passed. ``migrations/env.py`` calls
      ``fileConfig(config.config_file_name)`` whenever that attribute is set,
      which reconfigures the root logger from ``alembic.ini`` and would clobber
      pytest's logging capture for the rest of the session.

    The caller is responsible for having ``SQLALCHEMY_DATABASE_URI`` in the
    environment: ``env.py`` reads it first, ahead of ``Config``/``.env``.
    """
    cfg = AlembicConfig()
    cfg.set_main_option('script_location', str(REPO_ROOT / 'migrations'))
    return cfg


@contextmanager
def database_default(engine, collation, charset=REQUIRED_CHARSET):
    """Run the block with the DATABASE default set to ``charset``/``collation``.

    The point of every caller is the same: a schema built inside a database
    whose default is the target cannot be told apart from a schema that pins
    nothing, because both end up with the right collation. Building it inside a
    database whose default is WRONG is what turns the pinning into something a
    test can observe.

    Most callers vary only the COLLATION, which is what the schema pins per
    column, so ``charset`` defaults to ``REQUIRED_CHARSET``. It is a parameter
    rather than a constant because one refusal in the migration is keyed on the
    database CHARSET instead -- ``downgrade()`` will not convert back to a
    narrower default, since that would replace unrepresentable characters with
    ``?`` -- and a branch no test can reach is a branch that can be inverted or
    deleted with the tier still green.

    The restore is absolute rather than a save/restore: it goes back to exactly
    what the session-scoped ``integration_db_url`` fixture set, which is the
    only value any other test in the tier may observe. That fixture runs once,
    so a restore that merely undid the caller's own delta would leave the
    database wherever a previously-failed block had put it.
    """
    with engine.begin() as conn:
        conn.execute(sa.text(
            f'ALTER DATABASE `{engine.url.database}` '
            f'CHARACTER SET {charset} COLLATE {collation}'))
    try:
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(
                f'ALTER DATABASE `{engine.url.database}` CHARACTER SET '
                f'{REQUIRED_CHARSET} COLLATE {REQUIRED_COLLATION}'))


# Alembic's own bookkeeping table, excluded from every collation check in this
# tier: Alembic creates it itself, on its own terms, and no revision may assume
# anything about how. Excluded by NAME rather than by filtering to the model
# tables, so a stray or legacy table -- which `_drop_all_tables` exists because
# migration tests leave behind -- is still visible to the guards below.
ALEMBIC_TABLE = 'alembic_version'


def table_collations(engine) -> dict:
    """``{table: default collation}`` for every table but ``alembic_version``."""
    with engine.connect() as conn:
        rows = conn.execute(sa.text(
            'SELECT table_name, table_collation '
            'FROM information_schema.tables WHERE table_schema = database()'))
        return {row[0]: row[1] for row in rows if row[0] != ALEMBIC_TABLE}


def column_collations(engine) -> dict:
    """``{(table, column): collation}`` for every column that HAS a collation.

    ``collation_name`` is NULL for numeric, datetime and BLOB columns, so the
    filter is what confines this to the columns a collation can be pinned on.
    """
    with engine.connect() as conn:
        rows = conn.execute(sa.text(
            'SELECT table_name, column_name, collation_name '
            'FROM information_schema.columns WHERE table_schema = database() '
            'AND collation_name IS NOT NULL'))
        return {(row[0], row[1]): row[2] for row in rows
                if row[0] != ALEMBIC_TABLE}


def expected_column_collations() -> dict:
    """The collation every collatable column in the models must have.

    Derived from ``Base.metadata`` rather than hard-coded, so a column added
    later is covered on the day it is added rather than the day someone
    remembers to extend a list.

    Two type families qualify, and the second is easy to miss: every ``String``
    (``sa.Text`` is a ``String`` subclass, so it is included), and ``sa.JSON``,
    because MariaDB implements JSON as a ``LONGTEXT`` alias and therefore
    reports a collation for it -- a fixed ``utf8mb4_bin``, which
    ``CONVERT TO CHARACTER SET`` overwrites like any other text column and the
    migration restores explicitly. Asserting it is what keeps the migrated and
    the ``create_all`` schema equal on ``products.attributes``. BLOB columns
    (`photos.*_data`, `attachments.content`) have no collation at all.
    """
    expected = {}
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            key = (name, column.name)
            if isinstance(column.type, sa.JSON):
                expected[key] = BINARY_COLLATION
            elif isinstance(column.type, sa.String):
                expected[key] = (BINARY_COLLATION if key in BINARY_COLUMNS
                                 else REQUIRED_COLLATION)
    return expected


def assert_schema_is_pinned(engine) -> None:
    """Assert every table default and collatable column carries the pinned value.

    Shared by the two schema guards because they check the same claim against
    two INDEPENDENTLY maintained schemas -- ``create_all`` from the models in
    test_identifier_collation.py, the Alembic chain in test_migrations.py. What
    is deliberately not shared is the behavioral folding check each file keeps
    of its own: this one compares collation NAMES, which is the only way to see
    that the value stopped being whatever the server chose, while a folding
    probe is what proves the property the catalog actually depends on. Both are
    wanted, and neither subsumes the other.

    Both set comparisons are two-directional on purpose: a table or column the
    schema has and the models do not is exactly as interesting as the reverse,
    and pre-filtering either side to the models would make that undetectable.
    """
    observed_tables = table_collations(engine)
    assert set(observed_tables) == set(Base.metadata.tables), (
        f'schema tables and model tables disagree; only in the schema: '
        f'{sorted(set(observed_tables) - set(Base.metadata.tables))}, only in '
        f'the models: {sorted(set(Base.metadata.tables) - set(observed_tables))}')
    wrong_default = {table: collation
                     for table, collation in observed_tables.items()
                     if collation != REQUIRED_COLLATION}
    assert wrong_default == {}, (
        f'these tables do not default to {REQUIRED_COLLATION} and would '
        f'compare their strings under whatever the server chose: '
        f'{wrong_default}')

    observed = column_collations(engine)
    expected = expected_column_collations()
    assert set(observed) == set(expected), (
        f'collatable columns and model columns disagree; only in the schema: '
        f'{sorted(set(observed) - set(expected))}, only in the models: '
        f'{sorted(set(expected) - set(observed))}')
    mismatched = {key: (observed.get(key), value)
                  for key, value in expected.items()
                  if observed.get(key) != value}
    assert mismatched == {}, (
        f'columns whose collation is not the pinned one, as '
        f'(observed, expected): {mismatched}')


@pytest.fixture(scope='session')
def integration_db_url(mariadb_testcontainer) -> str:
    """The URL of the live MariaDB database these tests run against.

    Resolution order is ``SQLALCHEMY_DATABASE_URI`` then ``TestConfig``, and it
    has to be that way round: locally the container fixture exports the env var
    carrying its RANDOM host port, while ``TestConfig.SQLALCHEMY_DATABASE_URI``
    is a class attribute built from ``TEST_DB_*`` (default port 3307) when
    ``config`` is first imported -- ``TestConfig()`` only reads it back, it does
    not recompute anything, so anything that sets ``TEST_DB_*`` after that import
    is ignored. Under ``CI=true`` no container starts, the env var is whatever
    the workflow set (nothing), and the ``TEST_DB_*`` form is correct because the
    workflow exports those at job level, before any Python runs. This is also
    why ``tests/test_database.py::mariadb_engine`` is unusable here -- it
    resolves through ``TestConfig`` only.

    The resolved target is checked by ``_assert_safe_target`` before anything
    destructive touches it.

    The database default is then FORCED to utf8mb4 / utf8mb4_unicode_ci. The
    ``MARIADB_COLLATION_SERVER`` env var that ``mariadb_testcontainer`` (and the
    CI service container) sets is not a variable the official mariadb entrypoint
    interprets, so the server otherwise keeps its own built-in default -- which
    on 11.8 is ``utf8mb4_uca1400_ai_ci``, not ``utf8mb4_unicode_ci``. Forcing it
    makes the starting point a property of the harness rather than of the
    image's release notes, so the tier means the same thing on every MariaDB
    version.

    What that force is now FOR has changed, and it is worth being exact. It used
    to be the only thing setting the collation of any column, so the guard in
    test_identifier_collation.py could confirm only that the columns inherited
    what this fixture set -- it could not detect that a *deployment* got a
    different one, which is what DW-51 recorded. Since DW-34 the schema pins
    charset and collation itself (``app/database.py``'s MYSQL_TABLE_OPTIONS,
    migration a977ca7315df), so this ``ALTER DATABASE`` is a CONTRAST BASELINE:
    it fixes the value the schema would inherit if it pinned nothing, which is
    what makes ``assert_schema_is_pinned`` meaningful for the create_all schema
    and lets test_migrations.py flip the default to something else on purpose
    and still demand the pinned values. The behavioral folding assertions stay
    beside the name ones for the reason ``assert_schema_is_pinned`` gives.

    ``ALTER DATABASE`` needs only the ALTER privilege, which the container and
    the CI service container both grant the app user on its own database; if
    that ever stops being true this fixture fails loudly on the first test.
    """
    url = (os.environ.get('SQLALCHEMY_DATABASE_URI')
           or TestConfig().SQLALCHEMY_DATABASE_URI)
    parsed = _assert_safe_target(url)

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                f'ALTER DATABASE `{parsed.database}` '
                f'CHARACTER SET {REQUIRED_CHARSET} COLLATE {REQUIRED_COLLATION}'))
    finally:
        engine.dispose()

    return url


@pytest.fixture(scope='session')
def integration_engine(integration_db_url):
    """One Engine for the schema-management fixtures below.

    Session-scoped so the per-test drop/create cycle does not pay for a fresh
    connection pool each time; the service fixture builds its own engine because
    it goes through ``MariaDBStorage`` exactly as production does.
    """
    engine = create_engine(integration_db_url)
    yield engine
    engine.dispose()


def _drop_all_tables(engine) -> None:
    """Drop every table in the database, ``alembic_version`` included.

    Reflection-and-drop rather than ``DROP DATABASE``/``CREATE DATABASE``: the
    container's app user owns only ``workshop_inventory_test`` and has no
    CREATE-database privilege, and neither does the CI service container's user.
    ``FOREIGN_KEY_CHECKS=0`` removes the need to topologically sort the drops,
    so a partially-migrated schema (which is exactly what a failed migration
    test leaves behind) is still cleanable.

    The surrounding ``begin()`` is for connection handling, not atomicity --
    MySQL commits DDL implicitly, so a failure mid-loop leaves a half-dropped
    schema. That is survivable precisely because this runs on the way IN as well
    as out: the next test drops whatever is left.
    """
    metadata = sa.MetaData()
    with engine.begin() as conn:
        conn.execute(sa.text('SET FOREIGN_KEY_CHECKS = 0'))
        try:
            metadata.reflect(bind=conn)
            for table in metadata.tables.values():
                conn.execute(sa.schema.DropTable(table))
        finally:
            conn.execute(sa.text('SET FOREIGN_KEY_CHECKS = 1'))


@pytest.fixture
def blank_database(integration_engine):
    """An empty database -- no application tables, no ``alembic_version``.

    Function-scoped and dropping on the way IN as well as on the way out, so a
    test is unaffected by whatever the previous one left behind. That is what
    makes the acceptance criterion "any single file run alone, or the files run
    in any order, gives identical results" true: nothing here depends on file
    collection order.

    One caveat this cannot defend against: ``tests/conftest.py``'s ``e2e_server``
    is handed the *same* session-scoped container, hence the same database. The
    two tiers stay apart because ``nox -s integration`` selects ``-m integration``
    and ``nox -s e2e`` selects ``-m e2e``, never both. Collecting them into one
    process (a bare ``pytest``, or overriding the marker expression) would have
    this fixture drop the schema out from under a live e2e server -- so don't.
    """
    _drop_all_tables(integration_engine)
    yield integration_engine
    _drop_all_tables(integration_engine)


@pytest.fixture
def integration_schema(blank_database):
    """A blank database with the current ORM schema applied via ``create_all``.

    The service-level tests want the schema the models describe, not the one the
    migration chain happens to have built -- migration fidelity is
    test_migrations.py's subject, and coupling every service test to it would
    make one migration bug fail the whole tier.
    """
    Base.metadata.create_all(blank_database)
    return blank_database


@pytest.fixture
def integration_catalog_service(integration_schema, integration_db_url):
    """A ``CatalogService`` bound to the live MariaDB database.

    Built the production way -- ``MariaDBStorage`` first, service on top -- so
    the engine, pool and dialect under test are the deployed ones. The unit tier
    builds the same object over a temp SQLite file; that is the whole point of
    the comparison.
    """
    storage = MariaDBStorage(database_url=integration_db_url)
    result = storage.connect()
    assert result.success, f'could not connect to the integration database: {result.error}'
    try:
        yield CatalogService(storage)
    finally:
        storage.close()


@pytest.fixture
def integration_inventory_service(integration_schema, integration_db_url):
    """An ``InventoryService`` bound to the live MariaDB database.

    The inventory-side counterpart of ``integration_catalog_service``, built the
    same production way -- ``MariaDBStorage`` first, service on top -- so the
    engine, pool and DIALECT are the deployed ones. The dialect is the part this
    fixture exists for: ``get_field_value_suggestions`` now chooses its ORDER BY
    tiebreak on ``engine.dialect.name`` (``app/db.py``'s ``binary_order_key``),
    and the SQLite unit tier only ever exercises the identity branch of that
    choice.

    Each service fixture builds its own storage rather than sharing one: they
    are independent objects in production too, and a shared one would make the
    order the tests happen to request them observable through the pool.
    """
    storage = MariaDBStorage(database_url=integration_db_url)
    result = storage.connect()
    assert result.success, f'could not connect to the integration database: {result.error}'
    try:
        yield InventoryService(storage)
    finally:
        storage.close()
