"""Unit tests for the one-clock rule (feature 037, issue #134).

**Why these tests force a timezone.** The obvious version of
``test_a_product_records_its_times_on_one_clock`` -- create a product, count
it, assert the two timestamps agree -- passes against the *broken* code on a
machine whose local time is UTC. Unit tests run against SQLite, whose
``CURRENT_TIMESTAMP`` is UTC, so with ``TZ=UTC`` the server clock and the
application's local clock are the same clock and there is nothing to catch. CI
runners are routinely set to UTC. A regression test that is green on the bug is
worse than no test, so the tests that are about a *basis* run under
``forced_timezone`` and the ones that are about a *mechanism* patch the clock
instead.

**Why there are two kinds of test.** ``Column(default=...)`` binds its argument
at class-definition time, so patching ``app.database.utc_now`` afterwards
changes nothing about what a column default produces -- and under SQLite both
``func.now()`` and ``utc_now()`` yield UTC anyway, so no value-based assertion
can tell them apart. The column defaults are therefore tested structurally
(:class:`TestColumnDefaults`), while the explicit service writes, whose
``from ... import`` binding is resolved at call time, are tested by patching
the name in the module that calls it (:class:`TestExplicitWrites`).
"""

import inspect
import os
import time
from datetime import date, datetime, timedelta

import pytest

from app.catalog_service import CatalogService
from app.database import Base, MaterialTaxonomy, Product
from app.mariadb_materials_admin_service import (
    MariaDBMaterialsAdminService,
    TaxonomyAddRequest,
)
from app.product.routes import relative_age
from app.utils.clock import local_now, utc_now

# Four hours behind UTC in summer, five in winter -- either way, not UTC, which
# is the only property these tests need from it.
NON_UTC_ZONE = 'America/New_York'


@pytest.fixture
def forced_timezone():
    """Run the test with a process timezone that is not UTC.

    Restores whatever was there before, including the *absence* of TZ, because
    ``time.tzset()`` reads the environment and leaving it set would leak into
    every test that ran afterwards in the same process.
    """
    previous = os.environ.get('TZ')
    os.environ['TZ'] = NON_UTC_ZONE
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            del os.environ['TZ']
        else:
            os.environ['TZ'] = previous
        time.tzset()


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


def backdate(service, product_id, **fields):
    """Write a timestamp column directly, bypassing the service.

    Every path that records an age stamps it with now, so "counted three hours
    ago" is unreachable through the service. Same helper as
    ``tests/unit/test_stock_status.py:28``.
    """
    session = service.Session()
    try:
        product = session.query(Product).filter(Product.id == product_id).one()
        for name, value in fields.items():
            setattr(product, name, value)
        session.commit()
    finally:
        session.close()


class TestTheClockItself:
    """Both functions return naive datetimes, and they are different clocks"""

    def test_utc_now_is_naive(self):
        assert utc_now().tzinfo is None

    def test_local_now_is_naive(self):
        assert local_now().tzinfo is None

    def test_the_two_clocks_differ_by_the_zone_offset(self, forced_timezone):
        """Not a tautology: it is what makes every other test here meaningful.

        If this passes with a zero difference the fixture is not taking effect,
        and the basis tests below would pass against the broken code.
        """
        offset = utc_now() - local_now()
        assert offset > timedelta(hours=3)


class TestARecordedRowIsOnOneClock:
    """FR-001, FR-004, SC-001 -- issue #134, as an assertion"""

    def test_a_product_records_its_times_on_one_clock(self, service, forced_timezone):
        """The reported bug: 3:59:59 between two columns of one INSERT.

        ``date_added`` came from the column default (the database server, UTC)
        and ``quantity_updated_at`` from ``datetime.now()`` in the service
        (local), for two events in the same millisecond.
        """
        created = service.create_product(description='clock probe', quantity=1)
        product = service.get_product(created.id)

        assert abs(product.date_added - product.quantity_updated_at) < timedelta(minutes=1)
        assert abs(product.date_added - product.last_modified) < timedelta(minutes=1)

    def test_a_flag_is_on_the_same_clock_as_the_row(self, service, forced_timezone):
        created = service.create_product(description='clock probe')
        service.set_stock_status(created.id, 'low')
        product = service.get_product(created.id)

        assert product.stock_status_updated_at is not None
        assert abs(product.date_added - product.stock_status_updated_at) < timedelta(minutes=1)

    def test_no_recorded_time_is_in_the_future(self, service, forced_timezone):
        """FR-006. The direction matters as much as the size.

        Local time here runs behind UTC, so the pre-fix defect made
        ``date_added`` look four hours *ahead* of the count. A future-dated row
        renders as 'just now', which is exactly how this hid.
        """
        created = service.create_product(description='clock probe', quantity=1)
        product = service.get_product(created.id)
        now = utc_now()

        assert product.date_added <= now
        assert product.last_modified <= now
        assert product.quantity_updated_at <= now

    def test_a_material_records_its_times_on_one_clock(self, test_storage, forced_timezone):
        """The half of the defect that was never reported (research.md R1).

        ``material_taxonomy`` has the same shape as ``products``: the admin
        service passed a local ``datetime.now()`` over the UTC column defaults.
        """
        admin = MariaDBMaterialsAdminService(test_storage)
        ok, message = admin.add_taxonomy_entry(
            TaxonomyAddRequest(name='Clock Probe Steel', level=1)
        )
        assert ok, message

        session = admin.Session()
        try:
            material = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.name == 'Clock Probe Steel'
            ).one()
            date_added = material.date_added
            last_modified = material.last_modified
        finally:
            session.close()

        assert abs(utc_now() - date_added) < timedelta(minutes=1)
        assert abs(date_added - last_modified) < timedelta(minutes=1)


class TestColumnDefaults:
    """FR-002, FR-003, FR-012 -- the defaults are produced in Python.

    The only test that can see this. Under SQLite ``func.now()`` and
    ``utc_now()` both produce UTC, so the difference is structural, not
    observable in a value.
    """

    @staticmethod
    def _defaulted_datetime_columns():
        from sqlalchemy import DateTime

        found = []
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if not isinstance(column.type, DateTime):
                    continue
                if column.default is not None or column.onupdate is not None:
                    found.append((table.name, column.name, column))
        return found

    def test_every_defaulted_timestamp_uses_the_application_clock(self):
        """SQLAlchemy wraps a zero-argument callable default so it can be passed
        an execution context, and copies the original's ``__name__`` onto the
        wrapper -- so ``default.arg`` reprs as ``utc_now`` while not *being*
        it. ``inspect.unwrap`` follows the ``__wrapped__`` the wrapper sets.
        """
        columns = self._defaulted_datetime_columns()
        assert columns, 'no defaulted DateTime columns found -- the walk is wrong'

        for table_name, column_name, column in columns:
            where = f'{table_name}.{column_name}'
            for kind, default in (('default', column.default), ('onupdate', column.onupdate)):
                if default is None:
                    continue
                assert not default.is_clause_element, (
                    f'{where} {kind} is a SQL expression, so it takes the database '
                    f"server's clock (FR-003)"
                )
                assert inspect.unwrap(default.arg) is utc_now, (
                    f'{where} {kind} is not app.utils.clock.utc_now'
                )

    def test_every_defaulted_timestamp_produces_utc_not_local(self, forced_timezone):
        """The same claim, without reaching into SQLAlchemy's wrapping.

        If a future SQLAlchemy stops setting ``__wrapped__`` the test above
        turns into a false failure; this one keeps the requirement covered by
        calling the default and looking at which clock the answer came off.
        """
        for table_name, column_name, column in self._defaulted_datetime_columns():
            for kind, default in (('default', column.default), ('onupdate', column.onupdate)):
                if default is None:
                    continue
                produced = default.arg(None)
                where = f'{table_name}.{column_name} {kind}'
                assert abs(produced - utc_now()) < timedelta(minutes=1), (
                    f'{where} is not on the UTC clock'
                )
                assert abs(produced - local_now()) > timedelta(hours=3), (
                    f'{where} is on the local clock'
                )

    def test_the_defaulted_columns_are_the_ones_the_data_model_lists(self):
        """A new recorded column added on ``func.now()`` fails the test above.

        A new one added with no default at all would slip past it, so the set
        is pinned here as well -- these are the thirteen in data-model.md, the
        fifteen recorded columns less ``products.quantity_updated_at`` and
        ``products.stock_status_updated_at``, which are nullable and mean
        "nobody has counted this yet".
        """
        found = {
            (table, column) for table, column, _ in self._defaulted_datetime_columns()
        }

        assert found == {
            ('inventory_items', 'date_added'),
            ('inventory_items', 'last_modified'),
            ('material_taxonomy', 'date_added'),
            ('material_taxonomy', 'last_modified'),
            ('photos', 'created_at'),
            ('photos', 'updated_at'),
            ('item_photo_associations', 'created_at'),
            ('products', 'date_added'),
            ('products', 'last_modified'),
            ('purchases', 'date_added'),
            ('purchases', 'last_modified'),
            ('product_identifiers', 'date_added'),
            ('product_attachments', 'created_at'),
        }


class TestExplicitWrites:
    """INV-1, FR-012 -- the service writes come from the clock, not from now()"""

    def test_a_count_is_stamped_with_the_application_clock(self, service, monkeypatch):
        """Patches the name in ``app.catalog_service``, not in ``app.utils.clock``.

        ``from ... import utc_now`` binds a module global that the function
        looks up when it runs, so patching it here is what the call actually
        resolves. Patching ``app.utils.clock.utc_now`` would not reach it, and
        would not reach a ``Column(default=...)`` either -- hence
        :class:`TestColumnDefaults`.
        """
        sentinel = datetime(2026, 3, 14, 9, 26, 53)
        monkeypatch.setattr('app.catalog_service.utc_now', lambda: sentinel)

        created = service.create_product(description='clock probe', quantity=7)

        assert service.get_product(created.id).quantity_updated_at == sentinel

    def test_a_recount_is_stamped_with_the_application_clock(self, service, monkeypatch):
        created = service.create_product(description='clock probe', quantity=1)

        sentinel = datetime(2026, 3, 14, 9, 26, 53)
        monkeypatch.setattr('app.catalog_service.utc_now', lambda: sentinel)
        service.set_quantity(created.id, 4)

        assert service.get_product(created.id).quantity_updated_at == sentinel

    def test_a_flag_is_stamped_with_the_application_clock(self, service, monkeypatch):
        created = service.create_product(description='clock probe')

        sentinel = datetime(2026, 3, 14, 9, 26, 53)
        monkeypatch.setattr('app.catalog_service.utc_now', lambda: sentinel)
        service.set_stock_status(created.id, 'low')

        assert service.get_product(created.id).stock_status_updated_at == sentinel


class TestAgesAreComputedOnTheSameClock:
    """FR-007, INV-4 -- both ends of the subtraction share a basis.

    These are the only timestamps the operator ever sees, and they were correct
    before this feature because both halves were local. Moving the stored value
    to UTC without moving the comparison turns every count on the site into
    "counted just now": a stored UTC value is four hours ahead of a local
    ``datetime.now()``, and ``relative_age`` renders a negative age as 'just
    now' to absorb clock skew. That guard is why this would have gone unnoticed.
    """

    def test_a_count_taken_three_hours_ago_reads_as_three_hours(self, service, forced_timezone):
        product = service.create_product(description='clock probe', quantity=2)
        backdate(service, product.id, quantity_updated_at=utc_now() - timedelta(hours=3))

        age = service.get_product(product.id).quantity_age

        assert age is not None
        assert abs(age - timedelta(hours=3)) < timedelta(minutes=1)
        assert relative_age(age) == '3 hours ago'

    def test_a_flag_set_three_hours_ago_reads_as_three_hours(self, service, forced_timezone):
        product = service.create_product(description='clock probe')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=utc_now() - timedelta(hours=3))

        age = service.get_product(product.id).stock_status_age

        assert age is not None
        assert abs(age - timedelta(hours=3)) < timedelta(minutes=1)
        assert relative_age(age) == '3 hours ago'

    def test_a_fresh_count_does_not_read_as_stale(self, service, forced_timezone):
        """The other direction. A count taken now must not report four hours."""
        product = service.create_product(description='clock probe', quantity=2)

        age = service.get_product(product.id).quantity_age

        assert age < timedelta(minutes=1)
        assert relative_age(age) == 'just now'

    def test_an_uncounted_product_still_has_no_age(self, service, forced_timezone):
        """The double None guard is untouched: unknown is not an error."""
        product = service.create_product(description='clock probe')

        assert service.get_product(product.id).quantity_age is None
        assert service.get_product(product.id).stock_status_age is None


class TestStatedDaysStayOnTheOperatorsCalendar:
    """FR-008, INV-3 -- a day the operator states is not an instant.

    Sweeping these to UTC alongside the recorded timestamps would push an order
    captured at nine in the evening onto the following day, and the order
    listing renders the stored value directly. That is a visible bug traded for
    an invisible one, so these five call sites keep the local clock and say so
    by name.

    The clock is patched rather than read, because an assertion that only fails
    after 20:00 local is not a test.
    """

    # 21:00 local on 14 March. In UTC that is already the 15th, which is
    # precisely the day this must not record.
    EVENING = datetime(2026, 3, 14, 21, 0, 0)

    def test_an_order_captured_in_the_evening_takes_the_local_day(self, service, monkeypatch):
        monkeypatch.setattr('app.catalog_service.local_now', lambda: self.EVENING)

        purchase = service.capture_order(
            vendor='Amazon', description='clock probe', quantity=1, unit_price='1.00'
        )

        assert purchase.order_date == datetime(2026, 3, 14, 0, 0, 0)

    def test_a_receipt_in_the_evening_takes_the_local_day(self, service, monkeypatch):
        purchase = service.capture_order(
            vendor='Amazon', description='clock probe', quantity=1, unit_price='1.00',
            order_date=datetime(2026, 3, 1),
        )

        monkeypatch.setattr('app.catalog_service.local_now', lambda: self.EVENING)
        received = service.receive_purchase(purchase.id)

        assert received.received_date.date() == date(2026, 3, 14)

    def test_a_stated_order_date_is_stored_unshifted(self, service):
        """The operator typed it; nothing may move it."""
        stated = datetime(2026, 3, 14, 0, 0, 0)

        purchase = service.capture_order(
            vendor='Amazon', description='clock probe', quantity=1,
            unit_price='1.00', order_date=stated,
        )

        assert purchase.order_date == stated
