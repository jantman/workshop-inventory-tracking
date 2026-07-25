"""
Unit tests for the ProductTag ORM model (catalog subsystem, Story 3.3).

Exercises the ProductTag entity via the SQLite test engine
(Base.metadata.create_all). These tests validate the ORM class, not the Alembic
migration — the two are the only definitions of this table and nothing runs
Alembic here, so keep them in sync.
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Product, ProductTag


def _make_session(test_storage):
    """Build a session bound to the test engine (SQLite)."""
    Session = sessionmaker(bind=test_storage.engine)
    return Session()


def _make_product(session, internal_id, description='Tagged product'):
    """Persist a bare Product to hang tags off."""
    product = Product(internal_id=internal_id, description=description)
    session.add(product)
    session.commit()
    return product


class TestProductTagModel:
    """Tests for the ProductTag entity (FR16)."""

    @pytest.mark.unit
    def test_tablename_and_columns(self):
        """ProductTag maps to 'product_tags' with the FR16 columns."""
        assert ProductTag.__tablename__ == 'product_tags'
        cols = set(ProductTag.__table__.columns.keys())
        assert cols == {'id', 'product_id', 'tag', 'created_at'}

    @pytest.mark.unit
    def test_unique_constraint_is_named_and_on_the_pair(self):
        """'A tag is unique per Product' is DB-enforced over (product_id, tag)
        — the migration declares the same name."""
        constraints = {
            c.name: [col.name for col in c.columns]
            for c in ProductTag.__table__.constraints
            if c.name == 'uq_product_tags_product_tag'
        }
        assert constraints == {
            'uq_product_tags_product_tag': ['product_id', 'tag']}

    @pytest.mark.unit
    def test_persist_and_reload(self, test_storage):
        """A ProductTag persists and reloads with its fields intact."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session, 'PR0DTAG001')
            product_id = product.id
            tag = ProductTag(product_id=product_id, tag='ssr')
            session.add(tag)
            session.commit()
            tag_id = tag.id

            session.expunge_all()
            reloaded = session.get(ProductTag, tag_id)
            assert reloaded is not None
            assert reloaded.product_id == product_id
            assert reloaded.tag == 'ssr'
        finally:
            session.close()

    @pytest.mark.unit
    def test_created_at_autopopulates_and_is_write_once(self, test_storage):
        """created_at populates on insert; there is no updated_at (a tag row is
        never edited — it is added or removed)."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session, 'PR0DTAG002')
            tag = ProductTag(product_id=product.id, tag='rectifier')
            session.add(tag)
            session.commit()

            assert isinstance(tag.created_at, datetime)
            assert not hasattr(ProductTag, 'updated_at')
            assert 'updated_at' not in ProductTag.__table__.columns
        finally:
            session.close()

    @pytest.mark.unit
    def test_the_same_tag_on_two_products_is_allowed(self, test_storage):
        """Uniqueness is per Product — a shared tag is the whole point of the
        FR16 filter."""
        session = _make_session(test_storage)
        try:
            first = _make_product(session, 'PR0DTAG003')
            second = _make_product(session, 'PR0DTAG004')
            session.add(ProductTag(product_id=first.id, tag='ssr'))
            session.add(ProductTag(product_id=second.id, tag='ssr'))
            session.commit()

            rows = session.query(ProductTag).filter(ProductTag.tag == 'ssr').all()
            assert len(rows) == 2
        finally:
            session.close()

    @pytest.mark.unit
    def test_two_tags_on_one_product_are_allowed(self, test_storage):
        """A Product carries zero or more tags."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session, 'PR0DTAG005')
            session.add(ProductTag(product_id=product.id, tag='ssr'))
            session.add(ProductTag(product_id=product.id, tag='rectifier'))
            session.commit()

            rows = (session.query(ProductTag)
                    .filter(ProductTag.product_id == product.id).all())
            assert {row.tag for row in rows} == {'ssr', 'rectifier'}
        finally:
            session.close()

    @pytest.mark.unit
    def test_duplicate_product_tag_pair_rejected(self, test_storage):
        """The same tag twice on one Product violates the unique constraint."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session, 'PR0DTAG006')
            session.add(ProductTag(product_id=product.id, tag='ssr'))
            session.commit()

            session.add(ProductTag(product_id=product.id, tag='ssr'))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        finally:
            session.close()

    @pytest.mark.unit
    def test_to_dict(self, test_storage):
        """to_dict() returns the FR16 fields with an ISO-formatted timestamp."""
        session = _make_session(test_storage)
        try:
            product = _make_product(session, 'PR0DTAG007')
            tag = ProductTag(product_id=product.id, tag='heat sink')
            session.add(tag)
            session.commit()

            d = tag.to_dict()
            assert set(d.keys()) == {'id', 'product_id', 'tag', 'created_at'}
            assert d['product_id'] == product.id
            assert d['tag'] == 'heat sink'
            assert isinstance(d['created_at'], str)
            datetime.fromisoformat(d['created_at'])
        finally:
            session.close()

    @pytest.mark.unit
    def test_repr(self):
        """__repr__ is informative and does not raise."""
        tag = ProductTag(product_id=7, tag='ssr')
        r = repr(tag)
        assert 'ProductTag' in r
        assert 'ssr' in r
