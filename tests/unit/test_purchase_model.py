"""
Unit tests for the Purchase ORM model (catalog subsystem, Story 1.2).

Exercises the Purchase entity via the SQLite test engine (Base.metadata.create_all).
These tests validate the ORM class + Product<->Purchase relationship, not the
Alembic migration or DB-level FK enforcement (SQLite has foreign_keys OFF by
default) — keep the ORM columns and the migration DDL in sync.
"""

import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Product, Purchase


def _make_session(test_storage):
    """Build a session bound to the test engine (SQLite)."""
    Session = sessionmaker(bind=test_storage.engine)
    return Session()


def _make_product(session, **kwargs):
    """Persist and return a Product to hang purchases off of."""
    product = Product(description=kwargs.pop('description', 'Host product'), **kwargs)
    session.add(product)
    session.commit()
    return product


class TestPurchaseModel:
    """Tests for the Purchase enhanced-ORM entity."""

    @pytest.mark.unit
    def test_tablename_and_columns(self):
        """Purchase maps to the 'purchases' table with exactly the FR18 columns."""
        assert Purchase.__tablename__ == 'purchases'
        cols = set(Purchase.__table__.columns.keys())
        assert cols == {
            'id', 'product_id', 'vendor', 'vendor_sku', 'order_date',
            'received_date', 'quantity', 'unit_price', 'order_number',
            'source_url', 'request_key', 'created_at', 'updated_at',
        }

    @pytest.mark.unit
    def test_persist_and_reload(self, test_storage):
        """A Purchase persists and reloads with all fields intact."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            purchase = Purchase(
                product_id=product.id,
                vendor='DigiKey',
                vendor_sku='296-1234-5-ND',
                order_date=date(2026, 7, 1),
                received_date=date(2026, 7, 5),
                quantity=10,
                unit_price=Decimal('1.25'),
                order_number='PO-42',
                source_url='https://www.digikey.com/en/products/detail/x/y/123',
                request_key='req-abc-123',
            )
            session.add(purchase)
            session.commit()
            purchase_id = purchase.id

            session.expire_all()
            reloaded = session.get(Purchase, purchase_id)
            assert reloaded is not None
            assert reloaded.product_id == product.id
            assert reloaded.vendor == 'DigiKey'
            assert reloaded.vendor_sku == '296-1234-5-ND'
            assert reloaded.order_date == date(2026, 7, 1)
            assert reloaded.received_date == date(2026, 7, 5)
            assert reloaded.quantity == 10
            assert reloaded.order_number == 'PO-42'
            assert reloaded.source_url.startswith('https://www.digikey.com/')
            assert reloaded.request_key == 'req-abc-123'
        finally:
            session.close()

    @pytest.mark.unit
    def test_product_purchase_relationship(self, test_storage):
        """product.purchases <-> purchase.product navigate correctly (ORM)."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            p1 = Purchase(product=product, vendor='Mouser', unit_price=Decimal('2.00'))
            p2 = Purchase(product=product, vendor='DigiKey', unit_price=Decimal('2.10'))
            session.add_all([p1, p2])
            session.commit()

            session.expire_all()
            reloaded = session.get(Product, product.id)
            assert len(reloaded.purchases) == 2
            vendors = {pur.vendor for pur in reloaded.purchases}
            assert vendors == {'Mouser', 'DigiKey'}
            # reverse navigation
            assert reloaded.purchases[0].product.id == product.id
        finally:
            session.close()

    @pytest.mark.unit
    def test_null_received_date_allowed(self, test_storage):
        """A Purchase with NULL received_date persists (order in flight, FR19)."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            purchase = Purchase(product_id=product.id, vendor='Mouser', received_date=None)
            session.add(purchase)
            session.commit()

            session.expire_all()
            reloaded = session.get(Purchase, purchase.id)
            assert reloaded.received_date is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_unit_price_decimal_roundtrip(self, test_storage):
        """unit_price round-trips as a Decimal with 2dp precision."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            purchase = Purchase(product_id=product.id, unit_price=Decimal('12.50'))
            session.add(purchase)
            session.commit()

            session.expire_all()
            reloaded = session.get(Purchase, purchase.id)
            # SQLite has no native decimal; SQLAlchemy converts via float, so
            # compare on numeric value rather than exact Decimal repr.
            assert Decimal(str(reloaded.unit_price)) == Decimal('12.50')
        finally:
            session.close()

    @pytest.mark.unit
    def test_request_key_unique_non_null(self, test_storage):
        """A duplicate non-null request_key is rejected at commit."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            session.add(Purchase(product_id=product.id, request_key='dup-key'))
            session.commit()

            session.add(Purchase(product_id=product.id, request_key='dup-key'))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        finally:
            session.close()

    @pytest.mark.unit
    def test_request_key_multiple_nulls_allowed(self, test_storage):
        """Multiple rows with NULL request_key coexist (UNIQUE tolerates NULLs)."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            session.add(Purchase(product_id=product.id, request_key=None))
            session.add(Purchase(product_id=product.id, request_key=None))
            session.commit()  # must NOT raise

            count = session.query(Purchase).filter(Purchase.request_key.is_(None)).count()
            assert count == 2
        finally:
            session.close()

    @pytest.mark.unit
    def test_optional_fields_default_none(self, test_storage):
        """Only product_id is required; other business fields default to None."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            purchase = Purchase(product_id=product.id)
            session.add(purchase)
            session.commit()

            session.expire_all()
            reloaded = session.get(Purchase, purchase.id)
            for field in ('vendor', 'vendor_sku', 'order_date', 'received_date',
                          'quantity', 'unit_price', 'order_number', 'source_url',
                          'request_key'):
                assert getattr(reloaded, field) is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict(self, test_storage):
        """to_dict() returns the expected keys with serialized dates/price."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session)
            purchase = Purchase(
                product_id=product.id,
                vendor='DigiKey',
                order_date=date(2026, 7, 1),
                unit_price=Decimal('3.33'),
            )
            session.add(purchase)
            session.commit()

            d = purchase.to_dict()
            assert set(d.keys()) == {
                'id', 'product_id', 'vendor', 'vendor_sku', 'order_date',
                'received_date', 'quantity', 'unit_price', 'order_number',
                'source_url', 'request_key', 'created_at', 'updated_at',
            }
            assert d['vendor'] == 'DigiKey'
            assert d['order_date'] == '2026-07-01'
            assert d['received_date'] is None
            assert isinstance(d['unit_price'], float)
            assert d['unit_price'] == 3.33
            assert isinstance(d['created_at'], str)
        finally:
            session.close()

    @pytest.mark.unit
    def test_repr(self):
        """__repr__ is informative and does not raise."""
        purchase = Purchase(product_id=7, vendor='Mouser')
        r = repr(purchase)
        assert 'Purchase' in r
        assert 'Mouser' in r
