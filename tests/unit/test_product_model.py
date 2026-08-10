"""
Unit tests for the product catalog ORM models.

Covers app/database.py's Product, Purchase, ProductIdentifier, Tag and
ProductAttachment -- in particular the tri-state quantity default (FR-023) and
that a price round-trips as Decimal and never through binary floating point
(Constitution III).
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.database import (
    Product,
    ProductAttachment,
    ProductIdentifier,
    ProductSpecification,
    Purchase,
    Tag,
)


@pytest.fixture
def session(test_storage):
    """A session on the test database, through the project's storage fixture"""
    Session = sessionmaker(bind=test_storage.engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


def make_product(session, **overrides) -> Product:
    """Persist a minimal product and return it"""
    fields = {'description': 'Blue widget'}
    fields.update(overrides)
    product = Product(**fields)
    session.add(product)
    session.commit()
    return product


class TestProductDefaults:
    """A new product tracks nothing until told to (FR-023)"""

    def test_quantity_defaults_to_null(self):
        assert Product(description='x').quantity is None

    def test_quantity_defaults_to_null_after_a_round_trip(self, session):
        product = make_product(session)
        session.expire(product)
        assert product.quantity is None

    def test_a_new_product_is_not_tracked(self, session):
        assert make_product(session).is_tracked is False

    def test_stock_status_defaults_to_absent(self, session):
        assert make_product(session).stock_status is None

    def test_category_defaults_to_uncategorized(self, session):
        assert make_product(session).category_path is None

    def test_timestamps_are_set(self, session):
        product = make_product(session)
        assert product.date_added is not None
        assert product.last_modified is not None


class TestTriStateQuantity:
    """Zero and NULL are different facts and must stay distinguishable (SC-007)"""

    def test_zero_is_tracked(self, session):
        product = make_product(session, quantity=0)
        assert product.quantity == 0
        assert product.is_tracked is True

    def test_null_is_not_tracked(self, session):
        assert make_product(session, quantity=None).is_tracked is False

    def test_zero_and_null_are_not_equal(self, session):
        none_on_hand = make_product(session, description='counted, none left', quantity=0)
        untracked = make_product(session, description='never counted', quantity=None)
        assert none_on_hand.quantity != untracked.quantity
        assert none_on_hand.is_tracked != untracked.is_tracked


class TestDerivedStockState:
    """Derived at read time -- there is no stored status column to drift"""

    def test_threshold_low_when_at_the_threshold(self, session):
        product = make_product(session, quantity=2, reorder_threshold=2)
        assert product.is_threshold_low is True
        assert product.is_effectively_low is True

    def test_threshold_low_when_below_the_threshold(self, session):
        assert make_product(session, quantity=1, reorder_threshold=2).is_threshold_low is True

    def test_not_threshold_low_when_above(self, session):
        product = make_product(session, quantity=5, reorder_threshold=2)
        assert product.is_threshold_low is False
        assert product.is_effectively_low is False

    def test_untracked_product_is_never_threshold_low(self, session):
        assert make_product(session, quantity=None).is_threshold_low is False

    def test_tracked_without_a_threshold_is_not_threshold_low(self, session):
        assert make_product(session, quantity=0).is_threshold_low is False

    def test_manual_flag_is_independent_of_any_count(self, session):
        product = make_product(session, quantity=None, stock_status='low')
        assert product.is_manually_low is True
        assert product.is_effectively_low is True

    def test_manual_out_flag_counts_as_low(self, session):
        assert make_product(session, stock_status='out').is_manually_low is True


class TestQuantityAge:
    """FR-024: the age is what the operator judges, not a staleness flag"""

    def test_age_from_the_timestamp(self, session):
        stamped = datetime.now() - timedelta(days=240)
        product = make_product(session, quantity=3, quantity_updated_at=stamped)
        assert product.quantity_age is not None
        assert product.quantity_age.days >= 239

    def test_untracked_product_has_no_age(self, session):
        assert make_product(session, quantity=None).quantity_age is None

    def test_tracked_quantity_with_no_timestamp_yields_no_age_rather_than_an_error(self, session):
        product = make_product(session, quantity=3, quantity_updated_at=None)
        assert product.quantity_age is None


class TestPurchasePrice:
    """Constitution III: a price is a Decimal, start to finish"""

    def test_price_round_trips_as_decimal(self, session):
        product = make_product(session)
        purchase = Purchase(
            product_id=product.id,
            vendor='Amazon',
            unit_price=Decimal('12.34'),
        )
        session.add(purchase)
        session.commit()
        session.expire(purchase)

        assert isinstance(purchase.unit_price, Decimal)
        assert purchase.unit_price == Decimal('12.34')

    def test_a_price_that_binary_floating_point_would_mangle(self, session):
        product = make_product(session)
        purchase = Purchase(product_id=product.id, vendor='Amazon', unit_price=Decimal('0.10'))
        session.add(purchase)
        session.commit()
        session.expire(purchase)

        assert purchase.unit_price * 3 == Decimal('0.30')

    def test_to_dict_serializes_price_as_a_string_not_a_float(self, session):
        product = make_product(session)
        purchase = Purchase(product_id=product.id, vendor='Amazon', unit_price=Decimal('12.30'))
        session.add(purchase)
        session.commit()

        assert purchase.to_dict()['unit_price'] == '12.30'


class TestPurchaseState:
    """The timestamp is the state; there is no status column (FR-005)"""

    def test_no_received_date_means_outstanding(self, session):
        product = make_product(session)
        purchase = Purchase(product_id=product.id, vendor='Amazon')
        session.add(purchase)
        session.commit()
        assert purchase.is_outstanding is True

    def test_a_received_date_completes_it(self, session):
        product = make_product(session)
        purchase = Purchase(
            product_id=product.id, vendor='Amazon', received_date=datetime.now()
        )
        session.add(purchase)
        session.commit()
        assert purchase.is_outstanding is False


class TestIdentifiers:
    def test_internal_code_is_surfaced_from_the_identifier_rows(self, session):
        product = make_product(session)
        session.add(ProductIdentifier(
            product_id=product.id, id_type='INTERNAL', value='WIT0123456789', vendor=''
        ))
        session.commit()
        session.refresh(product)

        assert product.internal_code == 'WIT0123456789'

    def test_a_product_with_no_internal_row_reports_none(self, session):
        assert make_product(session).internal_code is None

    def test_the_unique_key_rejects_a_repeated_identifier(self, session):
        """FR-009 is a database property, not a convention"""
        first = make_product(session, description='first')
        second = make_product(session, description='second')

        session.add(ProductIdentifier(
            product_id=first.id, id_type='GTIN', value='00012345678905', vendor=''
        ))
        session.commit()

        session.add(ProductIdentifier(
            product_id=second.id, id_type='GTIN', value='00012345678905', vendor=''
        ))
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_the_same_value_under_two_vendors_is_two_rows(self, session):
        """FR-008: a vendor item id is only meaningful within its vendor"""
        first = make_product(session, description='first')
        second = make_product(session, description='second')

        session.add(ProductIdentifier(
            product_id=first.id, id_type='VENDOR', value='B0ABCDEFGH', vendor='Amazon'
        ))
        session.add(ProductIdentifier(
            product_id=second.id, id_type='VENDOR', value='B0ABCDEFGH', vendor='eBay'
        ))
        session.commit()

        assert session.query(ProductIdentifier).filter(
            ProductIdentifier.value == 'B0ABCDEFGH'
        ).count() == 2


class TestTags:
    def test_tags_attach_and_detach(self, session):
        product = make_product(session)
        tag = Tag(name='surplus')
        session.add(tag)
        session.commit()

        product.tags.append(tag)
        session.commit()
        assert [t.name for t in product.tags] == ['surplus']

        product.tags.remove(tag)
        session.commit()
        assert product.tags == []

    def test_a_tag_name_is_unique(self, session):
        session.add(Tag(name='surplus'))
        session.commit()

        session.add(Tag(name='surplus'))
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


class TestAttachmentOwnership:
    """Exactly one owner: a product or a purchase, never both and never neither"""

    def test_a_product_owned_attachment_is_valid(self, session, photo_row):
        product = make_product(session)
        attachment = ProductAttachment(photo_id=photo_row.id, product_id=product.id)
        session.add(attachment)
        session.commit()
        assert attachment.id is not None

    def test_a_purchase_owned_attachment_is_valid(self, session, photo_row):
        product = make_product(session)
        purchase = Purchase(product_id=product.id, vendor='Amazon')
        session.add(purchase)
        session.commit()

        attachment = ProductAttachment(photo_id=photo_row.id, purchase_id=purchase.id)
        session.add(attachment)
        session.commit()
        assert attachment.id is not None


class TestSpecifications:
    """A named value per row, ordered, serialized as a list (FR-006, FR-011)"""

    def test_to_dict_emits_a_list_in_display_order(self, session):
        product = make_product(session)
        # Added out of order deliberately: the relationship's order_by is what
        # has to put them right, not the insertion sequence.
        session.add_all([
            ProductSpecification(
                product_id=product.id, name='Output current', value='3 A',
                display_order=1
            ),
            ProductSpecification(
                product_id=product.id, name='Voltage', value='12 V',
                display_order=0
            ),
        ])
        session.commit()
        session.refresh(product)

        assert product.to_dict()['specifications'] == [
            {'name': 'Voltage', 'value': '12 V'},
            {'name': 'Output current', 'value': '3 A'},
        ]

    def test_to_dict_emits_an_empty_list_when_there_are_none(self, session):
        """Always present, never null -- an absent specification set is ordinary"""
        assert make_product(session).to_dict()['specifications'] == []

    def test_a_value_may_hold_a_multi_line_paragraph(self, session):
        """FR-003: this has to hold anything the old text column held"""
        paragraph = 'Voltage: 12 V\nCurrent: 3 A'
        product = make_product(session)
        session.add(ProductSpecification(
            product_id=product.id, name='Specifications', value=paragraph,
            display_order=0
        ))
        session.commit()
        session.refresh(product)

        assert product.specifications[0].value == paragraph

    def test_specifications_die_with_their_product(self, session):
        """delete-orphan, so nothing is left pointing at a product that is gone"""
        product = make_product(session)
        product.specifications.append(
            ProductSpecification(name='Voltage', value='12 V', display_order=0)
        )
        session.commit()

        session.delete(product)
        session.commit()

        assert session.query(ProductSpecification).count() == 0


@pytest.fixture
def photo_row(session):
    """A minimal row in the existing photos table to hang attachments from"""
    from app.database import Photo

    photo = Photo(
        filename='datasheet.pdf',
        content_type='application/pdf',
        file_size=4,
        thumbnail_data=b'thmb',
        medium_data=b'medm',
        original_data=b'orig',
    )
    session.add(photo)
    session.commit()
    return photo
