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
        """Product maps to 'products' with the FR2 columns + internal_id (2.4)."""
        assert Product.__tablename__ == 'products'
        cols = set(Product.__table__.columns.keys())
        assert cols == {
            'id', 'internal_id', 'manufacturer', 'mpn', 'description', 'notes',
            'category_path', 'attributes', 'created_at', 'updated_at',
            # Story 5.1
            'quantity_on_hand', 'quantity_verified_at', 'location',
            'sub_location',
        }

    @pytest.mark.unit
    def test_persist_and_reload(self, test_storage):
        """A Product persists and reloads with all FR2 fields intact."""
        session = _make_session(test_storage)
        try:
            product = Product(
                internal_id='PR0D000001',
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
            product = Product(internal_id='PR0D000002', description='Widget',
                              attributes=specs)
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
        """All FR2 fields except the PK/timestamps/internal_id accept NULL.

        internal_id is the one NOT NULL business column (Story 2.4): it has no
        DB default, so it must always be supplied by its sole writer.
        """
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000003')  # no other field at all
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
            # Story 5.1: all four are nullable with NO server default, so a bare
            # insert leaves the product UNTRACKED. `quantity_on_hand IS NULL` is
            # the state FR23 names, and a server default of 0 would silently
            # claim every product in the catalog had been counted and found
            # empty.
            assert reloaded.quantity_on_hand is None
            assert reloaded.quantity_verified_at is None
            assert reloaded.location is None
            assert reloaded.sub_location is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_quantity_zero_persists_distinctly_from_none(self, test_storage):
        """`0` and NULL are two different stored states, not one (FR23/FR24).

        The whole story rests on the column being able to tell "tracked, none on
        hand" from "not tracked", so this asserts it at the storage layer rather
        than trusting that Python's `0 is not None` survives a round trip
        through the driver — which is exactly where a NOT NULL column with a
        default, or a coercion in the model, would collapse the two.
        """
        session = _make_session(test_storage)
        try:
            tracked = Product(internal_id='PR0D000010', description='Counted',
                              quantity_on_hand=0,
                              quantity_verified_at=datetime(2026, 7, 29, 9, 0))
            untracked = Product(internal_id='PR0D000011',
                                description='Uncounted')
            session.add_all([tracked, untracked])
            session.commit()
            tracked_id, untracked_id = tracked.id, untracked.id

            session.expunge_all()
            reloaded_tracked = session.get(Product, tracked_id)
            reloaded_untracked = session.get(Product, untracked_id)
            assert reloaded_tracked.quantity_on_hand == 0
            assert reloaded_tracked.quantity_on_hand is not None
            assert reloaded_tracked.quantity_verified_at == \
                datetime(2026, 7, 29, 9, 0)
            assert reloaded_untracked.quantity_on_hand is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_location_pair_persists(self, test_storage):
        """The FR27 location pair round-trips; both are plain optional strings."""
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000012', description='Shelved',
                              location='Bin 7', sub_location='Left tray')
            session.add(product)
            session.commit()
            product_id = product.id

            session.expunge_all()
            reloaded = session.get(Product, product_id)
            assert reloaded.location == 'Bin 7'
            assert reloaded.sub_location == 'Left tray'
        finally:
            session.close()

    @pytest.mark.unit
    def test_timestamps_autopopulate(self, test_storage):
        """created_at and updated_at populate automatically on insert."""
        session = _make_session(test_storage)
        try:
            product = Product(internal_id='PR0D000004', description='Timestamped')
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
                internal_id='PR0D000005',
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
                'id', 'internal_id', 'manufacturer', 'mpn', 'description', 'notes',
                'category_path', 'attributes', 'created_at', 'updated_at',
                # Story 5.1 — this dict IS the audit snapshot, so a column
                # missing from it is a column no audit record can show changing.
                'quantity_on_hand', 'quantity_verified_at', 'location',
                'sub_location',
            }
            assert d['internal_id'] == 'PR0D000005'
            assert d['manufacturer'] == 'Bourns'
            assert d['mpn'] == '3386P-1-103'
            assert d['attributes'] == {'resistance': '10k'}
            # timestamps serialized as ISO strings
            assert isinstance(d['created_at'], str)
            datetime.fromisoformat(d['created_at'])
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict_carries_the_stock_columns(self, test_storage):
        """The four Story 5.1 columns appear with their stored values.

        `quantity_verified_at` is serialized like the other timestamps (ISO
        string, or None), and `quantity_on_hand` is emitted RAW so that the
        audit log records `0` as `0` rather than as an empty-looking value —
        the one thing the tri-state contract cannot afford to lose.
        """
        session = _make_session(test_storage)
        try:
            stamped = Product(internal_id='PR0D000013', description='Counted',
                              quantity_on_hand=0,
                              quantity_verified_at=datetime(2026, 7, 29, 9, 30),
                              location='Bin 7', sub_location='Left tray')
            untracked = Product(internal_id='PR0D000014', description='Bare')
            session.add_all([stamped, untracked])
            session.commit()

            d = stamped.to_dict()
            assert d['quantity_on_hand'] == 0
            assert d['quantity_verified_at'] == '2026-07-29T09:30:00'
            assert d['location'] == 'Bin 7'
            assert d['sub_location'] == 'Left tray'

            bare = untracked.to_dict()
            assert bare['quantity_on_hand'] is None
            assert bare['quantity_verified_at'] is None
            assert bare['location'] is None
            assert bare['sub_location'] is None
        finally:
            session.close()

    @pytest.mark.unit
    def test_repr(self):
        """__repr__ is informative and does not raise."""
        product = Product(internal_id='PR0D000006', mpn='LM317T',
                          description='regulator')
        r = repr(product)
        assert 'Product' in r
        assert 'LM317T' in r
