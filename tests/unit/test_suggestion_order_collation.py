"""
The dialect-aware ORDER BY tiebreak both suggestion readers share (DW-96).

`db.binary_order_key` exists because the two `get_field_value_suggestions`
methods end their sort with the raw column, and that key is only a TIEBREAK
under a collation that folds nothing. SQLite compares text byte-wise, so the
unit tier has always seen a total ordering; MariaDB's pinned
`utf8mb4_unicode_ci` folds case and accents, so `McMaster` and `mcmaster` tied
on every key there and the plan -- not the query -- chose which spelling the
operator was offered. The helper collates that one key to `utf8mb4_bin` on
MySQL/MariaDB and returns the column unchanged everywhere else.

Three claims are pinned here, and the last is the one that actually keeps the
two services honest:

* The branch itself, including that BOTH MySQL-family dialect names are
  recognized. A `mariadb+pymysql://` URL reports `dialect.name == 'mariadb'`,
  so a set holding only 'mysql' would silently fall through to the identity
  case under a perfectly ordinary deployment URL -- the same trap
  `app/database.py`'s `mysql_`/`mariadb_` kwarg pairs exist to avoid.
* The rendered SQL, per dialect, without a server -- the technique
  tests/unit/test_database_schema.py uses for the same reason: the failure mode
  is DDL/SQL that is wrong for a backend this session cannot reach.
* That each service really ROUTES its tiebreak through the helper. Every other
  assertion in this file would stay green if a service quietly went back to
  naming `column` directly, because under SQLite the two produce identical SQL
  and identical results. Only the integration tier
  (tests/integration/test_suggestion_order_collation.py) can observe the
  difference behaviorally, and it needs Docker; this is the part of the claim
  that can be checked on a laptop.
"""

import re

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect

from app.database import InventoryItem, Product, ProductTag
from app.db import BINARY_COLLATION, MYSQL_DIALECTS, binary_order_key
from app.mariadb_catalog_service import CatalogService
from app.mariadb_inventory_service import InventoryService

# Both dialects that reach a MariaDB server. Restated here rather than derived
# from MYSQL_DIALECTS so a change to that frozenset has to be made deliberately
# in two places instead of silently agreeing with itself -- the same duplication
# rule tests/unit/test_database_schema.py applies to the collation literals.
SERVER_DIALECTS = (mysql.dialect(), MariaDBDialect())

# Dialect names that must take the identity branch: the one the unit tier
# actually runs on, one this project does not use but SQLAlchemy knows, and the
# two non-answers a duck-typed or mock storage can produce for
# `engine.dialect.name`.
NON_SERVER_DIALECT_NAMES = ('sqlite', 'postgresql', '', None)


class TestBinaryOrderKeyBranch:
    """Which dialects get a collation, and which get their column back."""

    @pytest.mark.unit
    def test_both_mysql_family_names_are_recognized(self):
        """'mysql' and 'mariadb' are the same server reached two ways.

        Asserted on the frozenset rather than only through behavior so the
        failure names the omission directly: a set that lost 'mariadb' would
        otherwise surface as an ordering test failing on a real server, which
        is a long way from the one-word cause.
        """
        assert MYSQL_DIALECTS == frozenset({'mysql', 'mariadb'})

    @pytest.mark.unit
    @pytest.mark.parametrize('dialect_name', sorted(MYSQL_DIALECTS))
    def test_mysql_dialects_get_a_collated_key(self, dialect_name):
        result = binary_order_key(InventoryItem.vendor, dialect_name)
        assert result is not InventoryItem.vendor
        # `collate()` builds `<expr> COLLATE <clause>`; the right-hand side is
        # the collation itself, and reading it here (rather than only the
        # compiled string, which the class below covers) is what names the
        # WRONG-collation failure as such instead of as a text mismatch.
        assert result.right.collation == BINARY_COLLATION
        assert result.left is InventoryItem.vendor.__clause_element__()

    @pytest.mark.unit
    @pytest.mark.parametrize('dialect_name', NON_SERVER_DIALECT_NAMES)
    def test_every_other_dialect_gets_the_column_unchanged(self, dialect_name):
        """Identity, not merely an equivalent expression.

        SQLite has no `utf8mb4_bin`, so a collation clause leaking there is a
        syntax error rather than a no-op; and the `None`/`''` cases are what a
        duck-typed or mock storage produces, which must fall through to the
        column rather than raise.
        """
        assert binary_order_key(InventoryItem.vendor, dialect_name) is \
            InventoryItem.vendor


class TestRenderedOrderKey:
    """What each dialect actually compiles the key to, with no server."""

    @pytest.mark.unit
    @pytest.mark.parametrize('dialect', SERVER_DIALECTS,
                             ids=[d.name for d in SERVER_DIALECTS])
    def test_server_dialects_render_the_binary_collation(self, dialect):
        rendered = str(binary_order_key(InventoryItem.vendor,
                                        dialect.name).compile(dialect=dialect))
        assert f'COLLATE {BINARY_COLLATION}' in rendered
        assert 'vendor' in rendered

    @pytest.mark.unit
    def test_sqlite_renders_no_collation_at_all(self):
        dialect = sqlite.dialect()
        rendered = str(binary_order_key(InventoryItem.vendor,
                                        dialect.name).compile(dialect=dialect))
        assert 'COLLATE' not in rendered.upper()


def _record_order_key(monkeypatch, module_path):
    """Wrap ``binary_order_key`` in ``module_path`` with a recording delegator.

    Patched at the SERVICE module rather than at ``app.db``, because both
    services import the name (``from .db import binary_order_key``) and
    therefore hold their own reference -- patching the definition site would not
    be seen by either. The real helper is still called, so the query the service
    builds is the production one and the test observes rather than replaces it.

    Returns the list of ``(column, dialect_name)`` pairs the service passed.
    """
    calls = []
    real = binary_order_key

    def _recording(column, dialect_name):
        calls.append((column, dialect_name))
        return real(column, dialect_name)

    monkeypatch.setattr(f'{module_path}.binary_order_key', _recording)
    return calls


def _executed_statements(engine):
    """Record every statement ``engine`` executes; returns the growing list."""
    statements = []

    @event.listens_for(engine, 'before_cursor_execute')
    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    return statements


def _order_by_clause(statement):
    """The text after the LAST ``ORDER BY`` in ``statement``.

    Taking the last one keeps a subquery's own ordering (there is none today,
    but the method is free to grow one) from being mistaken for the outer sort.

    Matched with a case-insensitive regex rather than by slicing the original
    at offsets measured on ``statement.upper()``: case mapping is not
    length-preserving in general (``'ß'.upper()`` is two characters), so an
    offset taken from the uppercased copy is only reliably an offset into the
    original while the SQL stays ASCII. It does today -- literals are bound
    parameters -- which is exactly the kind of premise that stops holding
    quietly.
    """
    matches = list(re.finditer(r'\sORDER\s+BY\s', statement, re.IGNORECASE))
    assert matches, f'statement has no ORDER BY to inspect: {statement}'
    return statement[matches[-1].end():]


def _assert_sorts_on(statement, column_sql):
    """Assert the sort ends with exactly ``LOWER(col), col`` and nothing after.

    This is the assertion that makes the recording tests above mean what they
    claim. Observing that the helper was CALLED does not prove its result is
    what the query sorts by: `order_by(rank, lower(c), binary_order_key(c), c)`
    calls it exactly once, renders identically under SQLite, and silently
    restores the plan-dependent tiebreak on MariaDB. It is caught here because
    the clause would then end `..., lower(c), c, c` -- the LAST term is no
    longer preceded by the LOWER() key, so the tail below stops matching.

    Only the tail is asserted, not a count of the column's appearances: in the
    ranked branch the `rank` CASE is itself part of this clause and names the
    column several times, which is correct and says nothing about the tiebreak.
    """
    clause = _order_by_clause(statement)
    assert clause.endswith(f'lower({column_sql}), {column_sql}'), (
        f'sort does not end with the LOWER()/tiebreak pair: {clause}')


class TestInventoryServiceRoutesThroughTheHelper:
    """`InventoryService.get_field_value_suggestions` asks the shared helper."""

    @pytest.fixture
    def service(self, test_storage):
        # No Flask app: `resolve_engine` adopts the storage's own engine and
        # never reaches `current_app`, so an app context is not load-bearing
        # for anything this class asserts. (The catalog class below is built
        # the same way.)
        return InventoryService(test_storage)

    @pytest.mark.unit
    def test_unfiltered_ordering_uses_the_helper(self, service, monkeypatch):
        calls = _record_order_key(monkeypatch, 'app.mariadb_inventory_service')

        service.get_field_value_suggestions('vendor')

        assert len(calls) == 1
        column, dialect_name = calls[0]
        assert column is InventoryItem.vendor
        assert dialect_name == service.engine.dialect.name == 'sqlite'

    @pytest.mark.unit
    def test_ranked_ordering_uses_the_helper_too(self, service, monkeypatch):
        """The `query` branch builds its own `order_by`, so it is a second call
        site and can drift from the first independently."""
        calls = _record_order_key(monkeypatch, 'app.mariadb_inventory_service')

        service.get_field_value_suggestions('vendor', query='mc')

        assert len(calls) == 1
        column, dialect_name = calls[0]
        assert column is InventoryItem.vendor
        assert dialect_name == 'sqlite'

    @pytest.mark.unit
    def test_the_scoped_field_passes_its_own_column(self, service, monkeypatch):
        """`sub_location` sorts on `sub_location`, not on the `location` it is
        filtered by -- the tiebreak has to follow the SELECTed column."""
        calls = _record_order_key(monkeypatch, 'app.mariadb_inventory_service')

        service.get_field_value_suggestions('sub_location', location='Shelf A')

        assert [column for column, _ in calls] == [InventoryItem.sub_location]

    @pytest.mark.unit
    def test_no_collate_reaches_sqlite(self, service):
        """The acceptance criterion, observed on the wire rather than inferred.

        The identity branch is what keeps this true, and a regression here is
        not subtle -- SQLite rejects `COLLATE utf8mb4_bin` outright -- but the
        assertion is cheap and states the invariant where a reader of the
        service will look for it. The shape of the sort is asserted alongside
        it, because "no COLLATE" alone would also hold for a query with no
        tiebreak, or no ORDER BY, at all.
        """
        statements = _executed_statements(service.engine)

        service.get_field_value_suggestions('vendor')
        service.get_field_value_suggestions('vendor', query='mc')

        assert statements, 'the service issued no statement to observe'
        assert not [s for s in statements if 'COLLATE' in s.upper()]
        for statement in statements:
            _assert_sorts_on(statement, 'inventory_items.vendor')


class TestCatalogServiceRoutesThroughTheHelper:
    """The catalog half, which must stay identical to the inventory half."""

    @pytest.fixture
    def service(self, test_storage):
        return CatalogService(test_storage)

    @pytest.mark.unit
    @pytest.mark.parametrize('field, expected_column', [
        ('category_path', Product.category_path),
        ('tags', ProductTag.tag),
    ])
    def test_unfiltered_ordering_uses_the_helper(self, service, monkeypatch,
                                                 field, expected_column):
        """Both whitelisted fields, because the column resolves through
        `_FIELD_SUGGESTION_MODELS` and `tags` is the one sourced from a child
        table -- a tiebreak that sorted on the parent's column instead would be
        a different query with the same shape."""
        calls = _record_order_key(monkeypatch, 'app.mariadb_catalog_service')

        service.get_field_value_suggestions(field)

        assert len(calls) == 1
        column, dialect_name = calls[0]
        assert column is expected_column
        assert dialect_name == service.engine.dialect.name == 'sqlite'

    @pytest.mark.unit
    def test_ranked_ordering_uses_the_helper_too(self, service, monkeypatch):
        calls = _record_order_key(monkeypatch, 'app.mariadb_catalog_service')

        service.get_field_value_suggestions('category_path', query='elec')

        assert len(calls) == 1
        column, dialect_name = calls[0]
        assert column is Product.category_path
        assert dialect_name == 'sqlite'

    @pytest.mark.unit
    def test_no_collate_reaches_sqlite(self, service):
        statements = _executed_statements(service.engine)

        service.get_field_value_suggestions('category_path')
        service.get_field_value_suggestions('category_path', query='elec')

        assert statements, 'the service issued no statement to observe'
        assert not [s for s in statements if 'COLLATE' in s.upper()]
        for statement in statements:
            _assert_sorts_on(statement, 'products.category_path')

    @pytest.mark.unit
    def test_the_child_table_field_sorts_on_its_own_column(self, service):
        """`tags` selects from `product_tags`, so its sort must name that
        column and not the parent's."""
        statements = _executed_statements(service.engine)

        service.get_field_value_suggestions('tags')

        assert statements, 'the service issued no statement to observe'
        assert not [s for s in statements if 'COLLATE' in s.upper()]
        for statement in statements:
            _assert_sorts_on(statement, 'product_tags.tag')
