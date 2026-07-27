"""
``CatalogService.create_product``'s internal_id retry, against InnoDB.

The unit tier (tests/unit/test_catalog_service.py::TestInternalIdGeneration)
covers the same three outcomes on SQLite, and for the foreign-IntegrityError
case it has to *fake* the failure by wrapping the session so ``flush()`` raises.
That proves the branch is reachable; it does not prove the branch is the one a
real backend takes. What is only checked here:

* MariaDB/InnoDB surfaces a UNIQUE violation at ``flush()`` and not deferred to
  COMMIT -- the retry loop only wraps the flush, so a backend that deferred the
  check would fall straight through to the generic handler and return None
  instead of retrying.
* ``_internal_id_is_taken``'s post-rollback re-query works after a real InnoDB
  statement rollback (the session is usable again, and the row it looks for is
  the committed one, not part of the aborted attempt).
* A genuine non-collision IntegrityError, raised by the database itself rather
  than by a test double, is re-raised inside the loop instead of burning the
  retry budget.
"""

import pytest
import sqlalchemy as sa

from app.database import Product, ProductIdentifier
from app.mariadb_catalog_service import INTERNAL_ID_MAX_ATTEMPTS

# Candidate values the monkeypatched generator hands out. All canonical
# (10 characters of Crockford base-32) so nothing here depends on the column
# tolerating a shape the system never issues.
FRESH = 'FRESH00001'
DERIVED_ROW_ONLY = 'DER1VEDR0W'
NON_COLLIDING = 'F0RE1GN001'

# The duplicated MPN used to force a non-collision IntegrityError, plus the name
# of the temporary index that makes it one.
DUP_MPN = 'DUP-MPN'
TEMP_MPN_INDEX = 'tmp_uq_products_mpn'


def _fake_generator(monkeypatch, values):
    """Point ``generate_internal_id`` at a fixed sequence; return the call log.

    Patched at ``app.utils.internal_id.generate_internal_id`` because the
    service calls it as a module attribute. This is the one substitution the
    integration tier allows: it forces a *candidate* collision, but the database
    still decides whether that candidate is actually taken -- which is the
    behavior under test.
    """
    calls = []
    remaining = iter(values)

    def _generate(**kwargs):
        calls.append(1)
        try:
            return next(remaining)
        except StopIteration:
            # create_product wraps its whole retry loop in `except Exception`,
            # and StopIteration is one -- an exhausted list would surface as
            # `create_product` returning None and the assertion failing on a
            # value, with nothing pointing at the real cause. Fail here instead.
            pytest.fail(
                f'the service drew more than the {len(values)} candidate(s) '
                f'this test supplies; INTERNAL_ID_MAX_ATTEMPTS or the retry '
                f'policy changed')

    monkeypatch.setattr('app.utils.internal_id.generate_internal_id', _generate)
    return calls


def _always_generate(monkeypatch, value):
    """Point ``generate_internal_id`` at one value forever; return the call log.

    The unbounded counterpart to ``_fake_generator``, for the exhaustion case
    where the number of draws is the thing under test rather than a precondition.
    """
    calls = []

    def _generate(**kwargs):
        calls.append(1)
        return value

    monkeypatch.setattr('app.utils.internal_id.generate_internal_id', _generate)
    return calls


def _products_with(service, value):
    session = service.Session()
    try:
        return (session.query(Product)
                .filter(Product.internal_id == value).all())
    finally:
        session.close()


def _internal_rows(service, value=None):
    session = service.Session()
    try:
        query = (session.query(ProductIdentifier)
                 .filter(ProductIdentifier.identifier_type == 'INTERNAL'))
        if value is not None:
            query = query.filter(ProductIdentifier.value == value)
        return query.all()
    finally:
        session.close()


def _product_count(service):
    session = service.Session()
    try:
        return session.query(Product).count()
    finally:
        session.close()


class TestInternalIdRetryAgainstInnoDB:
    """The retry loop with a real UNIQUE constraint doing the arbitration."""

    @pytest.mark.integration
    def test_collision_on_the_column_retries_with_a_fresh_candidate(
            self, integration_catalog_service, monkeypatch):
        """A candidate already held by a committed Product is rejected by
        ``uq_products_internal_id`` and retried; the generator is drawn from
        once per attempt and the landing product carries the fresh value."""
        service = integration_catalog_service
        first = service.create_product(description='product A')
        # create_product converts any failure to None, so an unchecked setup
        # failure would surface below as AttributeError on None rather than as
        # itself.
        assert first is not None, 'setup failed: create_product returned None'
        taken = service.get_product(first).internal_id

        calls = _fake_generator(monkeypatch, [taken, taken, FRESH])

        second = service.create_product(description='product B')
        assert isinstance(second, int)
        assert service.get_product(second).internal_id == FRESH
        # Three attempts: two rejected by the database, one accepted.
        assert len(calls) == 3

        # The colliding value is still held by exactly one Product and one
        # derived row -- neither rolled-back attempt left a partial write.
        assert [p.id for p in _products_with(service, taken)] == [first]
        assert len(_internal_rows(service, taken)) == 1
        assert len(_internal_rows(service, FRESH)) == 1
        assert _internal_rows(service, FRESH)[0].product_id == second

    @pytest.mark.integration
    def test_collision_on_the_derived_row_alone_also_retries(
            self, integration_catalog_service, monkeypatch):
        """An INTERNAL identifier row whose value no Product holds still forces
        a retry.

        Both unique constraints have to be able to trigger the loop:
        ``uq_product_identifiers_type_value_scope`` is what the derived row hits,
        and ``_internal_id_is_taken`` has to recognize that hit as a collision
        after the rollback or the error would be re-raised as foreign.
        """
        service = integration_catalog_service
        host = service.create_product(description='host')
        assert host is not None, 'setup failed: create_product returned None'

        session = service.Session()
        try:
            session.add(ProductIdentifier(product_id=host,
                                          identifier_type='INTERNAL',
                                          value=DERIVED_ROW_ONLY,
                                          vendor_scope=''))
            session.commit()
        finally:
            session.close()
        assert _products_with(service, DERIVED_ROW_ONLY) == []

        calls = _fake_generator(monkeypatch, [DERIVED_ROW_ONLY, FRESH])

        product_id = service.create_product(description='product B')
        assert product_id is not None, 'the retry did not commit'
        assert service.get_product(product_id).internal_id == FRESH
        assert len(calls) == 2
        # The bare row is neither duplicated nor claimed by the new product.
        assert len(_internal_rows(service, DERIVED_ROW_ONLY)) == 1


    @pytest.mark.integration
    def test_retry_budget_exhausted_writes_nothing(
            self, integration_catalog_service, monkeypatch):
        """A candidate that is always taken burns the budget and writes nothing.

        The other end of the loop, and the one where a backend difference would
        be most expensive: if InnoDB deferred the UNIQUE check to COMMIT, the
        rollback-and-reclassify path would never run and this would fail with a
        partially written product rather than a clean give-up. The service
        converts the exhaustion RuntimeError into None at its outer handler.
        """
        service = integration_catalog_service
        first = service.create_product(description='product A')
        assert first is not None, 'setup failed: create_product returned None'
        taken = service.get_product(first).internal_id

        calls = _always_generate(monkeypatch, taken)

        assert service.create_product(description='product B') is None
        assert len(calls) == INTERNAL_ID_MAX_ATTEMPTS
        assert _product_count(service) == 1
        # The existing holder is untouched: no attempt left a partial write.
        assert [p.id for p in _products_with(service, taken)] == [first]
        assert len(_internal_rows(service, taken)) == 1


class TestNonCollisionIntegrityError:
    """An IntegrityError the retry cannot fix must not be retried."""

    @pytest.fixture
    def unique_mpn_index(self, integration_catalog_service):
        """A temporary UNIQUE index on ``products.mpn``.

        The catalog schema has no second unique constraint on ``products``, so
        there is no way to make the real backend raise a non-collision
        IntegrityError without adding one. An index is used rather than a test
        double precisely because the point is that the *database* raises: the
        service must then find the candidate untaken, re-raise, and give up.
        Dropped afterwards so nothing leaks into another test.
        """
        engine = integration_catalog_service.engine
        with engine.begin() as conn:
            conn.execute(sa.text(
                f'CREATE UNIQUE INDEX {TEMP_MPN_INDEX} ON products (mpn)'))
        yield
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP INDEX {TEMP_MPN_INDEX} ON products'))

    @pytest.mark.integration
    def test_foreign_integrity_error_is_not_retried(
            self, integration_catalog_service, unique_mpn_index, monkeypatch):
        """A duplicate MPN fails the insert, the candidate is found untaken, and
        ``create_product`` gives up after exactly one candidate -- returning
        None rather than looping against a condition no new candidate can fix.
        """
        service = integration_catalog_service
        assert service.create_product(description='first', mpn=DUP_MPN) is not None
        before = _product_count(service)

        calls = _fake_generator(monkeypatch, [NON_COLLIDING])

        assert service.create_product(description='second', mpn=DUP_MPN) is None
        assert len(calls) == 1
        assert _product_count(service) == before
        # Nothing from the aborted attempt survived, on either table.
        assert _products_with(service, NON_COLLIDING) == []
        assert _internal_rows(service, NON_COLLIDING) == []
