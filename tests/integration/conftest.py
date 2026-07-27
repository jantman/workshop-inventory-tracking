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
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

from app.database import Base
from app.mariadb_catalog_service import CatalogService
from app.mariadb_storage import MariaDBStorage
from config import TestConfig

# tests/integration/conftest.py -> tests/integration -> tests -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# The collation every folding assumption in the catalog subsystem rests on.
# Asserted by tests/integration/test_identifier_collation.py and forced by
# `integration_db_url` below; see that fixture for why forcing is necessary.
REQUIRED_COLLATION = 'utf8mb4_unicode_ci'
REQUIRED_CHARSET = 'utf8mb4'

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

    The database is then FORCED to utf8mb4 / utf8mb4_unicode_ci. This is not
    belt-and-braces: the ``MARIADB_COLLATION_SERVER`` env var that
    ``mariadb_testcontainer`` (and the CI service container) sets is not a
    variable the official mariadb entrypoint interprets, so the server keeps its
    own built-in default -- which on 11.8 is ``utf8mb4_uca1400_ai_ci``, not
    ``utf8mb4_unicode_ci``. Forcing it here makes the collation under test a
    property of the harness rather than of the image's release notes, so the
    tier means the same thing on every MariaDB version.

    Be honest about what that costs: because the schema pins no collation of its
    own (DW-51), the guard in test_identifier_collation.py can only confirm that
    the columns inherited what this fixture set -- it cannot detect that a
    *deployment* got a different one. It therefore also asserts that the
    collation actually folds case and accents, which is the property the catalog
    subsystem depends on and the only one worth guarding.

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
