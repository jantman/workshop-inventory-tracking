"""
Unit tests for the Product ORM model (catalog subsystem, Story 1.1).

Exercises the Product entity via the SQLite test engine (Base.metadata.create_all).
These tests validate the ORM class, not the Alembic migration — keep the two in sync.
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import sessionmaker

from app.database import Product


def _make_session(test_storage):
    """Build a session bound to the test engine (SQLite)."""
    Session = sessionmaker(bind=test_storage.engine)
    return Session()


class TestProductModel:
    """Tests for the Product enhanced-ORM entity."""

    @pytest.mark.unit
    def test_tablename_and_columns(self):
        """Product maps to the 'products' table with exactly the FR2 columns."""
        assert Product.__tablename__ == 'products'
        cols = set(Product.__table__.columns.keys())
        assert cols == {
            'id', 'manufacturer', 'mpn', 'description', 'notes',
            'category_path', 'attributes', 'created_at', 'updated_at',
        }

    @pytest.mark.unit
    def test_persist_and_reload(self, test_storage):
        """A Product persists and reloads with all FR2 fields intact."""
        session = _make_session(test_storage)
        try:
            product = Product(
                manufacturer='Texas Instruments',
                mpn='LM317T',
                description='LM317 adjustable voltage regulator, TO-220',
                notes='Bought a reel of these',
                category_path='electronics/power/linear-regulators',
                attributes={'package': 'TO-220', 'v_out_max': '37V'},
            )
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded is not None
            assert reloaded.manufacturer == 'Texas Instruments'
            assert reloaded.mpn == 'LM317T'
            assert reloaded.description == 'LM317 adjustable voltage regulator, TO-220'
            assert reloaded.notes == 'Bought a reel of these'
            assert reloaded.category_path == 'electronics/power/linear-regulators'
        finally:
            session.close()

    @pytest.mark.unit
    def test_attributes_json_roundtrip(self, test_storage):
        """The attributes JSON column round-trips a Python dict."""
        session = _make_session(test_storage)
        try:
            specs = {'voltage': '12V', 'pins': 8, 'rohs': True, 'tags': ['a', 'b']}
            product = Product(description='Widget', attributes=specs)
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.attributes == specs
            assert reloaded.attributes['pins'] == 8
            assert reloaded.attributes['tags'] == ['a', 'b']
        finally:
            session.close()

    @pytest.mark.unit
    def test_optional_fields_default_none(self, test_storage):
        """All FR2 fields except the PK/timestamps accept NULL (backfill-forward)."""
        session = _make_session(test_storage)
        try:
            product = Product()  # no fields supplied at all
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.manufacturer is None
            assert reloaded.mpn is None
            assert reloaded.description is None
            assert reloaded.notes is None
            assert reloaded.category_path is None
            assert reloaded.attributes is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_timestamps_autopopulate(self, test_storage):
        """created_at and updated_at populate automatically on insert."""
        session = _make_session(test_storage)
        try:
            product = Product(description='Timestamped')
            session.add(product)
            session.commit()

            assert isinstance(product.created_at, datetime)
            assert isinstance(product.updated_at, datetime)
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict(self, test_storage):
        """to_dict() returns the FR2 fields with ISO-formatted timestamps."""
        session = _make_session(test_storage)
        try:
            product = Product(
                manufacturer='Bourns',
                mpn='3386P-1-103',
                description='10k trimmer potentiometer',
                category_path='electronics/passives/potentiometers',
                attributes={'resistance': '10k'},
            )
            session.add(product)
            session.commit()

            d = product.to_dict()
            assert set(d.keys()) == {
                'id', 'manufacturer', 'mpn', 'description', 'notes',
                'category_path', 'attributes', 'created_at', 'updated_at',
            }
            assert d['manufacturer'] == 'Bourns'
            assert d['mpn'] == '3386P-1-103'
            assert d['attributes'] == {'resistance': '10k'}
            # timestamps serialized as ISO strings
            assert isinstance(d['created_at'], str)
            datetime.fromisoformat(d['created_at'])
        finally:
            session.close()

    @pytest.mark.unit
    def test_repr(self):
        """__repr__ is informative and does not raise."""
        product = Product(mpn='LM317T', description='regulator')
        r = repr(product)
        assert 'Product' in r
        assert 'LM317T' in r
