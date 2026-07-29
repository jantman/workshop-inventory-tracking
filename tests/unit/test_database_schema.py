"""
Unit-tier guard on the charset/collation decisions DW-34 encodes -- in
`app/database.py` for the `create_all` schema, and in migration a977ca7315df
for a deployed one.

These are assertions about DDL, not about data, so they need no database
server at all: SQLAlchemy renders `CREATE TABLE` for a named dialect off the
metadata, and the migration's dialect guard is observable against a throwaway
SQLite file. That is the point of doing it here rather than only in the
integration tier -- the failures this catches are a model change that renders
the WRONG DDL and a migration that stops no-opping off MariaDB, and the
integration tier can only see the first after a `create_all` or an upgrade
against a live MariaDB, which a laptop without Docker never runs, while it
cannot see the second at all.

Three claims are pinned, and each has a plausible way of silently regressing:

* Every table declares `mysql_charset`/`mysql_collate` AND the `mariadb_`
  pair, because SQLAlchemy resolves dialect kwargs on `dialect.name` and a
  `mariadb+pymysql://` URL reports 'mariadb' rather than 'mysql'. A table added
  later without them -- or a pin declared for only one of the two names --
  inherits `@@collation_database`, which on MariaDB 11.8 is
  `utf8mb4_uca1400_ai_ci`, not the collation this codebase's folding
  assumptions are written against. Nothing else in the unit suite would notice,
  because SQLite has no per-table charset.
* `products.internal_id` and `products.stock_status` carry their `utf8mb4_bin`
  collation through a `.with_variant()`, so it reaches MySQL DDL and NOT SQLite
  DDL. A bare `String(32, collation='utf8mb4_bin')` renders `COLLATE
  utf8mb4_bin` into the SQLite DDL too, which that backend rejects on
  `create_all` -- that failure is loud, but the reverse (dropping the collation
  entirely and quietly restoring the DW-73 case-folding divergence, or Story
  5.3's `stock_status IN ('low','out')` matching `'LOW'` on the server and not
  in Python) is not, and this file's job is the reverse case. Neither pin
  closes trailing-space equality -- `utf8mb4_bin` is PAD SPACE -- which the
  integration tier records explicitly.
* Migration a977ca7315df no-ops on any non-MySQL dialect. Its DDL is
  MariaDB-only (`CONVERT TO CHARACTER SET`, `MODIFY`), and the guard is one
  `if` at the top of each direction -- easy to drop while refactoring, and
  nothing else would notice, because the rest of the chain is never run against
  SQLite either. See `test_the_migration_no_ops_off_mysql` for why "the whole
  chain applies to SQLite" is NOT the claim.

The model half and the migration half are maintained independently; the
integration tier is what compares the two resulting schemas.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect
from sqlalchemy.schema import CreateTable

from app.database import MYSQL_TABLE_OPTIONS, Base, Product

# tests/unit/test_database_schema.py -> tests/unit -> tests -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# The revision under test and the one it follows.
COLLATION_REVISION = 'a977ca7315df'
BEFORE_COLLATION = '68707d1f48bf'

# Both dialects that reach a MariaDB server, because they are NOT the same
# object to SQLAlchemy: `mysql+pymysql://` gives `dialect.name == 'mysql'` and
# `mariadb+pymysql://` gives `'mariadb'`, and dialect-scoped kwargs and
# `with_variant()` both resolve on that name. A pin declared for only one of
# them silently vanishes under the other URL scheme -- which is the whole
# defect DW-34 exists to fix, reintroduced by the fix for it.
SERVER_DIALECTS = (mysql.dialect(), MariaDBDialect())

# The collation every folding assumption in the catalog subsystem rests on, and
# the binary exception. Restated here as literals rather than imported from
# app.database, so a change to the constant there has to be made deliberately
# in two places instead of silently agreeing with itself.
EXPECTED_CHARSET = 'utf8mb4'
EXPECTED_COLLATION = 'utf8mb4_unicode_ci'
BINARY_COLLATION = 'utf8mb4_bin'

# Every column allowed to override the table default, as (table, column).
# Restated rather than imported from tests/integration/conftest.py for the same
# reason as the collation literals above, and with the same consequence worth
# being explicit about: adding a binary column fails BOTH this module's
# `test_the_binary_columns_are_the_only_collation_overrides` and the integration
# tier's `assert_schema_is_pinned` until it is declared in both places. Two loud
# failures naming the same new column, not one silent divergence -- which is the
# property that makes the duplication safe.
BINARY_COLUMNS = {
    ('products', 'internal_id'),
    ('products', 'stock_status'),
}


@pytest.mark.unit
def test_every_table_pins_the_charset_and_collation():
    """No table is left inheriting the server's default collation.

    Driven off `Base.metadata` rather than a hard-coded list, so a table added
    tomorrow is covered the day it is added rather than the day someone
    remembers to extend this test.
    """
    missing = {}
    for name, table in Base.metadata.tables.items():
        for prefix in ('mysql', 'mariadb'):
            if (table.kwargs.get(f'{prefix}_charset') != EXPECTED_CHARSET
                    or table.kwargs.get(f'{prefix}_collate') != EXPECTED_COLLATION):
                missing[(name, prefix)] = dict(table.kwargs)
    assert missing == {}, (
        f'these (table, dialect) pairs do not pin '
        f'{EXPECTED_CHARSET}/{EXPECTED_COLLATION} and would inherit whatever '
        f'the server default happens to be: {missing}. Add MYSQL_TABLE_OPTIONS '
        f'as the trailing dict of __table_args__.')


@pytest.mark.unit
def test_the_shared_options_dict_is_not_mutated_by_declarative():
    """`MYSQL_TABLE_OPTIONS` is one object shared by all nine tables.

    Sharing it is what makes the decision single-sourced, but it is only safe
    while nothing pops entries out of it -- if declarative ever consumed the
    dict, the first table mapped would keep the options and every table mapped
    afterwards would silently lose them. Stated as its own test so that failure
    is diagnosed rather than merely observed above.
    """
    assert MYSQL_TABLE_OPTIONS == {
        'mysql_charset': EXPECTED_CHARSET,
        'mysql_collate': EXPECTED_COLLATION,
        'mariadb_charset': EXPECTED_CHARSET,
        'mariadb_collate': EXPECTED_COLLATION,
    }


@pytest.mark.unit
@pytest.mark.parametrize('column_name', ['internal_id', 'stock_status'])
def test_the_binary_columns_are_binary_on_the_server_and_bare_on_sqlite(
        column_name):
    """The `.with_variant()` really is dialect-scoped, on BOTH server dialects.

    `utf8mb4_bin` is what makes MariaDB agree with Python about each of these
    columns: `Product.internal_id == value` with `is_valid_internal_id`'s
    deliberate case-sensitivity (DW-73), and `stock_status IN ('low','out')`
    with `Product.is_effective_low`'s frozenset membership (Story 5.3, AD-6).
    Both would agree with SQLite's binary comparison and disagree with a
    folding MariaDB.

    The SQLite half of the assertion is the one that keeps the whole unit suite
    runnable -- a bare `collation=` renders COLLATE into SQLite DDL and
    `create_all` fails on it; the 'mariadb' half is the one that keeps the pin
    from evaporating under a `mariadb+pymysql://` URL.
    """
    column_type = Product.__table__.c[column_name].type

    for dialect in SERVER_DIALECTS:
        assert column_type.compile(dialect) == \
            f'VARCHAR(32) COLLATE {BINARY_COLLATION}', (
                f'{column_name} is not binary under dialect {dialect.name!r}')

    assert column_type.compile(sqlite.dialect()) == 'VARCHAR(32)'


@pytest.mark.unit
def test_server_create_table_carries_the_table_default_and_the_overrides():
    """The rendered `CREATE TABLE` states every decision, in one statement.

    Compiling the DDL rather than reading the metadata is deliberate: the
    metadata can hold options a dialect never renders -- `mysql_charset` under
    the 'mariadb' dialect is exactly that case -- and it is the rendered
    statement that a deployment gets.

    Both binary columns are named literally rather than looped over
    `BINARY_COLUMNS`, because what is being asserted here is the rendered TEXT
    of the clause (type, width and collation together) and not merely that a
    COLLATE appeared -- which is what the enumeration test below covers.
    """
    for dialect in SERVER_DIALECTS:
        ddl = str(CreateTable(Product.__table__).compile(dialect=dialect))

        assert f'CHARSET={EXPECTED_CHARSET}' in ddl, (
            f'no charset rendered under dialect {dialect.name!r}: {ddl}')
        assert f'COLLATE {EXPECTED_COLLATION}' in ddl, (
            f'no table collation rendered under dialect {dialect.name!r}: {ddl}')
        assert f'internal_id VARCHAR(32) COLLATE {BINARY_COLLATION}' in ddl, (
            f'internal_id not binary under dialect {dialect.name!r}: {ddl}')
        assert f'stock_status VARCHAR(32) COLLATE {BINARY_COLLATION}' in ddl, (
            f'stock_status not binary under dialect {dialect.name!r}: {ddl}')


@pytest.mark.unit
def test_sqlite_ddl_declares_no_collation_at_all():
    """Nothing MySQL-only leaks into the schema the unit tier builds.

    SQLite accepts a `COLLATE` clause naming only its three built-ins, so any
    MySQL collation reaching this DDL is an error on `create_all` -- and a
    `CHARSET=` suffix is a syntax error outright. Checked across every table
    because the leak would come from a new column, not from `products`.
    """
    for name, table in Base.metadata.tables.items():
        ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
        assert 'COLLATE' not in ddl.upper(), (
            f'SQLite DDL for {name} carries a COLLATE clause: {ddl}')
        assert 'CHARSET' not in ddl.upper(), (
            f'SQLite DDL for {name} carries a CHARSET clause: {ddl}')


@pytest.mark.unit
def test_the_binary_columns_are_the_only_collation_overrides():
    """The binary exceptions stay exceptions, and stay these TWO.

    Both are closed machine vocabularies that code compares for equality or
    membership, never operator-typed prose, and in both cases the folding table
    default made MariaDB disagree with Python:

    * `products.internal_id` (DW-73) -- `is_valid_internal_id` is deliberately
      case-SENSITIVE ("silently upper-casing input would let two different
      scanned strings map to one identifier"), so under a folding collation
      `resolve_scan`'s `Product.internal_id == value` lands a lower-cased scan
      on a product in production and falls through to a free-text search under
      SQLite.
    * `products.stock_status` (Story 5.3) -- `Product.is_effective_low`'s SQL
      half is `stock_status IN ('low','out')`, which a case- and
      accent-folding collation makes TRUE for `'LOW'`, `'Low'` and `'lòw'`
      while the Python getter's frozenset membership is FALSE for all three.
      AD-6 requires the two encodings to agree row for row, and they would not
      on any row a hand-run UPDATE or a restored backup left behind.

    Every OTHER string column must keep folding, and adding a third entry here
    is a semantics change in whichever service reads it rather than a schema
    detail. `product_identifiers.value` is the sharpest case:
    `add_identifier`'s duplicate rejection is written against the folding
    collation, so pinning it binary would let two identifiers differing only in
    case both be stored. The tag and category paths are the same -- their
    collision and non-canonical-overlap refusals fold by design, and Epic 3's
    canonical-path rules assume it.

    Enumerated by rendering the server DDL, so it sees exactly what the server
    would.
    """
    for dialect in SERVER_DIALECTS:
        overriding = set()
        for name, table in Base.metadata.tables.items():
            for column in table.columns:
                if 'COLLATE' in column.type.compile(dialect).upper():
                    overriding.add((name, column.name))

        assert overriding == BINARY_COLUMNS, (
            f'under dialect {dialect.name!r} the columns overriding the table '
            f'collation are {overriding}, expected {BINARY_COLUMNS}')


@pytest.mark.unit
def test_the_migration_no_ops_off_mysql(tmp_path, monkeypatch):
    """a977ca7315df applies and reverses against SQLite by doing nothing.

    Be exact about the claim, because the obvious stronger one is false: the
    chain as a whole does NOT apply to SQLite and never has --
    dce1254cd381 issues `ALTER TABLE ... MODIFY COLUMN ... MEDIUMBLOB`, which
    SQLite rejects outright. So the database here is STAMPED at the preceding
    revision rather than migrated up to it, and what is exercised is exactly
    this revision's two dialect guards.

    They earn their place: without them an upgrade run against any non-MariaDB
    URL dies on `CONVERT TO CHARACTER SET`, and there is nothing to pin on
    SQLite anyway -- its comparisons are already binary, and making the two
    backends agree is DW-72, an app-level engine change.
    """
    monkeypatch.setenv('SQLALCHEMY_DATABASE_URI',
                       f'sqlite:///{tmp_path / "dialect_guard.db"}')
    # No config FILE: migrations/env.py calls fileConfig() whenever one is set,
    # which would reconfigure the root logger from alembic.ini and clobber
    # pytest's capture for the rest of the session.
    config = AlembicConfig()
    config.set_main_option('script_location', str(REPO_ROOT / 'migrations'))

    # Same guard, and same reason, as the integration tier's
    # TestPinnedCollations: a revision inserted between these two would be run
    # against SQLite by the `upgrade` below -- almost certainly MySQL-only DDL
    # -- and the failure would point at the wrong migration.
    assert ScriptDirectory.from_config(config).get_revision(
        COLLATION_REVISION).down_revision == BEFORE_COLLATION, (
            f'{COLLATION_REVISION} no longer follows {BEFORE_COLLATION} '
            f'directly; update the constants in this module')

    command.stamp(config, BEFORE_COLLATION)
    command.upgrade(config, COLLATION_REVISION)
    command.downgrade(config, BEFORE_COLLATION)
