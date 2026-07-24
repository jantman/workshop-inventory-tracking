"""
Unit tests for CatalogService (catalog subsystem, Story 1.3).

Exercises product create / get / update via the SQLite test engine
(the `test_storage` fixture). Mirrors the InventoryService test approach.
"""

import pytest

from app.mariadb_catalog_service import CatalogService


@pytest.fixture
def catalog_service(test_storage):
    return CatalogService(test_storage)


class TestCatalogServiceCreate:

    @pytest.mark.unit
    def test_create_with_only_description(self, catalog_service):
        """A Product created with only a Label Description saves; other fields NULL."""
        new_id = catalog_service.create_product(description='LM317 regulator')
        assert isinstance(new_id, int)

        product = catalog_service.get_product(new_id)
        assert product is not None
        assert product.description == 'LM317 regulator'
        assert product.manufacturer is None
        assert product.mpn is None
        assert product.category_path is None
        assert product.notes is None
        assert product.attributes is None

    @pytest.mark.unit
    def test_create_with_all_fields(self, catalog_service):
        new_id = catalog_service.create_product(
            manufacturer='TI',
            mpn='LM317T',
            description='LM317 adjustable regulator',
            notes='reel of these',
            category_path='electronics/power/regulators',
        )
        product = catalog_service.get_product(new_id)
        assert product.manufacturer == 'TI'
        assert product.mpn == 'LM317T'
        assert product.description == 'LM317 adjustable regulator'
        assert product.notes == 'reel of these'
        assert product.category_path == 'electronics/power/regulators'

    @pytest.mark.unit
    def test_blank_optional_fields_coerced_to_none(self, catalog_service):
        """Empty-string optional fields are stored as NULL, not ''."""
        new_id = catalog_service.create_product(
            description='  Widget  ',
            manufacturer='',
            mpn='   ',
            category_path='',
            notes='',
        )
        product = catalog_service.get_product(new_id)
        assert product.description == 'Widget'  # trimmed
        assert product.manufacturer is None
        assert product.mpn is None
        assert product.category_path is None
        assert product.notes is None


class TestCatalogServiceGet:

    @pytest.mark.unit
    def test_get_missing_returns_none(self, catalog_service):
        assert catalog_service.get_product(999999) is None


class TestCatalogServiceUpdate:

    @pytest.mark.unit
    def test_update_changes_persist(self, catalog_service):
        from datetime import datetime
        from sqlalchemy.orm import sessionmaker
        from app.database import Product

        new_id = catalog_service.create_product(description='original')

        # Backdate updated_at so the onupdate bump is observable (func.now()
        # has second resolution — asserting >= creation time is tautological).
        backdated = datetime(2020, 1, 1, 12, 0, 0)
        Session = sessionmaker(bind=catalog_service.engine)
        session = Session()
        try:
            session.query(Product).filter(Product.id == new_id).update(
                {'updated_at': backdated}, synchronize_session=False)
            session.commit()
        finally:
            session.close()

        ok = catalog_service.update_product(new_id, description='changed', manufacturer='Bourns')
        assert ok is True

        after = catalog_service.get_product(new_id)
        assert after.description == 'changed'
        assert after.manufacturer == 'Bourns'
        # onupdate must have replaced the backdated timestamp
        assert after.updated_at > backdated

    @pytest.mark.unit
    def test_update_missing_returns_false(self, catalog_service):
        assert catalog_service.update_product(999999, description='nope') is False

    @pytest.mark.unit
    def test_update_blank_optional_coerced_to_none(self, catalog_service):
        new_id = catalog_service.create_product(description='keep', manufacturer='TI')
        catalog_service.update_product(new_id, manufacturer='')
        product = catalog_service.get_product(new_id)
        assert product.manufacturer is None


class TestCatalogServicePurchases:

    @pytest.mark.unit
    def test_record_purchase_creates_and_attaches(self, catalog_service):
        from datetime import date
        from decimal import Decimal
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.record_purchase(
            pid, vendor='DigiKey', unit_price=Decimal('1.50'),
            quantity=10, order_date=date(2026, 7, 1))
        assert isinstance(snap, dict)
        assert snap['product_id'] == pid
        assert snap['vendor'] == 'DigiKey'

        purchases = catalog_service.get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].vendor == 'DigiKey'
        assert purchases[0].product_id == pid

    @pytest.mark.unit
    def test_record_purchase_defaults_order_date_to_today(self, catalog_service):
        from datetime import date
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.record_purchase(pid, vendor='Mouser')
        assert snap['order_date'] == date.today().isoformat()

    @pytest.mark.unit
    def test_record_purchase_missing_product_returns_none(self, catalog_service):
        assert catalog_service.record_purchase(999999, vendor='X') is None

    @pytest.mark.unit
    def test_get_purchases_chronological_order(self, catalog_service):
        from datetime import date
        pid = catalog_service.create_product(description='widget')
        catalog_service.record_purchase(pid, vendor='B', order_date=date(2026, 7, 5))
        catalog_service.record_purchase(pid, vendor='A', order_date=date(2026, 7, 1))
        catalog_service.record_purchase(pid, vendor='C', order_date=date(2026, 7, 9))
        purchases = catalog_service.get_purchases_for_product(pid)
        assert [p.vendor for p in purchases] == ['A', 'B', 'C']

    @pytest.mark.unit
    def test_get_purchases_empty_for_unknown_product(self, catalog_service):
        assert catalog_service.get_purchases_for_product(999999) == []

    @pytest.mark.unit
    def test_get_last_paid_price_most_recent_priced(self, catalog_service):
        from datetime import date
        from decimal import Decimal
        pid = catalog_service.create_product(description='widget')
        catalog_service.record_purchase(pid, order_date=date(2026, 7, 1), unit_price=Decimal('1.00'))
        catalog_service.record_purchase(pid, order_date=date(2026, 7, 9), unit_price=Decimal('2.50'))
        # a later-dated purchase with NO price must be skipped
        catalog_service.record_purchase(pid, order_date=date(2026, 7, 12), unit_price=None)
        assert catalog_service.get_last_paid_price(pid) == Decimal('2.50')

    @pytest.mark.unit
    def test_get_last_paid_price_none_when_unpriced(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        catalog_service.record_purchase(pid, vendor='X', unit_price=None)
        assert catalog_service.get_last_paid_price(pid) is None


_PDF_BYTES = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF'


class TestCatalogServiceAttachments:

    @pytest.mark.unit
    def test_add_attachment_to_product(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_attachment(
            product_id=pid, filename='ds.pdf', content=_PDF_BYTES,
            content_type='application/pdf')
        assert snap['product_id'] == pid
        assert snap['purchase_id'] is None
        assert snap['filename'] == 'ds.pdf'
        assert snap['file_size'] == len(_PDF_BYTES)
        assert 'content' not in snap  # BLOB never serialized

        rows = catalog_service.get_attachments_for_product(pid)
        assert len(rows) == 1
        assert rows[0].filename == 'ds.pdf'

    @pytest.mark.unit
    def test_add_attachment_to_purchase(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.record_purchase(pid, vendor='DigiKey')
        purchase_id = snap['id']
        att = catalog_service.add_attachment(
            purchase_id=purchase_id, filename='receipt.pdf', content=_PDF_BYTES,
            content_type='application/pdf')
        assert att['purchase_id'] == purchase_id
        assert att['product_id'] is None

    @pytest.mark.unit
    def test_add_attachment_xor_both_owners_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.record_purchase(pid, vendor='X')
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=pid, purchase_id=snap['id'], filename='x.pdf',
                content=_PDF_BYTES, content_type='application/pdf')

    @pytest.mark.unit
    def test_add_attachment_xor_no_owner_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                filename='x.pdf', content=_PDF_BYTES, content_type='application/pdf')

    @pytest.mark.unit
    def test_add_attachment_oversize_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        from app.mariadb_catalog_service import ATTACHMENT_MAX_SIZE
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=pid, filename='big.pdf',
                content=b'x' * (ATTACHMENT_MAX_SIZE + 1),
                content_type='application/pdf')

    @pytest.mark.unit
    def test_add_attachment_disallowed_type_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=pid, filename='x.svg', content=b'<svg/>',
                content_type='image/svg+xml')

    @pytest.mark.unit
    def test_add_attachment_empty_content_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=pid, filename='x.pdf', content=b'',
                content_type='application/pdf')

    @pytest.mark.unit
    def test_add_attachment_missing_owner_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=999999, filename='x.pdf', content=_PDF_BYTES,
                content_type='application/pdf')

    @pytest.mark.unit
    def test_get_attachments_empty_and_ordered(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        assert catalog_service.get_attachments_for_product(pid) == []
        catalog_service.add_attachment(product_id=pid, filename='a.pdf',
                                       content=_PDF_BYTES, content_type='application/pdf')
        catalog_service.add_attachment(product_id=pid, filename='b.pdf',
                                       content=_PDF_BYTES, content_type='application/pdf')
        rows = catalog_service.get_attachments_for_product(pid)
        assert [r.filename for r in rows] == ['a.pdf', 'b.pdf']

    @pytest.mark.unit
    def test_get_attachments_defers_blob(self, catalog_service):
        """AC #4: listing must NOT load the BLOB content column."""
        from sqlalchemy import inspect
        pid = catalog_service.create_product(description='widget')
        catalog_service.add_attachment(product_id=pid, filename='a.pdf',
                                       content=_PDF_BYTES, content_type='application/pdf')
        rows = catalog_service.get_attachments_for_product(pid)
        # 'content' is deferred → reported as unloaded on the returned row.
        assert 'content' in inspect(rows[0]).unloaded

    @pytest.mark.unit
    def test_add_attachment_overlong_filename_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_attachment(
                product_id=pid, filename='x' * 300 + '.pdf', content=_PDF_BYTES,
                content_type='application/pdf')

    @pytest.mark.unit
    def test_get_attachment_data(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_attachment(
            product_id=pid, filename='ds.pdf', content=_PDF_BYTES,
            content_type='application/pdf')
        result = catalog_service.get_attachment_data(snap['id'])
        assert result == (_PDF_BYTES, 'application/pdf', 'ds.pdf')
        assert catalog_service.get_attachment_data(999999) is None
