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


class TestCatalogServiceIdentifiers:

    @pytest.mark.unit
    @pytest.mark.parametrize('itype, value, expected', [
        # GTIN is normalized to its 14-digit key; every other type stores the
        # value as entered. GTIN_UNVALIDATED is global and stored as-entered.
        ('GTIN', '012345678905', '00012345678905'),
        ('GTIN_UNVALIDATED', 'ABC123', 'ABC123'),
        ('ASIN', 'ABC123', 'ABC123'),
        ('FNSKU', 'ABC123', 'ABC123'),
        ('MPN', 'ABC123', 'ABC123'),
        ('VENDOR_SKU', 'ABC123', 'ABC123'),
        ('INTERNAL', 'ABC123', 'ABC123'),
    ])
    def test_add_each_type_persists(self, catalog_service, itype, value, expected):
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type=itype, value=value, vendor='Acme')
        assert snap['product_id'] == pid
        assert snap['identifier_type'] == itype
        assert snap['value'] == expected
        rows = catalog_service.get_identifiers_for_product(pid)
        assert len(rows) == 1
        assert rows[0].identifier_type == itype

    @pytest.mark.unit
    def test_add_identifier_accepts_enum_member(self, catalog_service):
        from app.models import IdentifierType
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type=IdentifierType.MPN, value='LM317')
        assert snap['identifier_type'] == 'MPN'

    @pytest.mark.unit
    def test_duplicate_global_pair_rejected_names_product(self, catalog_service):
        from app.exceptions import ValidationError
        from sqlalchemy.exc import IntegrityError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        catalog_service.add_identifier(pid_a, identifier_type='GTIN', value='00012345678905')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.add_identifier(pid_b, identifier_type='GTIN', value='00012345678905')
        # Caught domain error, NOT an IntegrityError...
        assert not isinstance(exc_info.value, IntegrityError)
        # ...naming the conflicting product (A).
        assert str(pid_a) in str(exc_info.value)

    @pytest.mark.unit
    def test_same_vendor_sku_different_vendors_both_persist(self, catalog_service):
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        snap_a = catalog_service.add_identifier(
            pid_a, identifier_type='VENDOR_SKU', value='X', vendor='Acme')
        snap_b = catalog_service.add_identifier(
            pid_b, identifier_type='VENDOR_SKU', value='X', vendor='Zed')
        assert snap_a['vendor_scope'] == 'Acme'
        assert snap_b['vendor_scope'] == 'Zed'

    @pytest.mark.unit
    def test_same_vendor_sku_same_vendor_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        catalog_service.add_identifier(
            pid_a, identifier_type='VENDOR_SKU', value='X', vendor='Acme')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.add_identifier(
                pid_b, identifier_type='VENDOR_SKU', value='X', vendor='Acme')
        assert str(pid_a) in str(exc_info.value)

    @pytest.mark.unit
    def test_gtin_ignores_vendor_arg(self, catalog_service):
        from app.exceptions import ValidationError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        snap = catalog_service.add_identifier(
            pid_a, identifier_type='GTIN', value='012345678905', vendor='Acme')
        # GTIN is global → vendor ignored → vendor_scope is the '' sentinel.
        assert snap['vendor_scope'] == ''
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(
                pid_b, identifier_type='GTIN', value='012345678905', vendor='Zed')

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_value', ['', '   '])
    def test_blank_value_rejected(self, catalog_service, bad_value):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(pid, identifier_type='MPN', value=bad_value)

    @pytest.mark.unit
    def test_invalid_type_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(pid, identifier_type='NOPE', value='ABC')

    @pytest.mark.unit
    def test_unknown_product_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(999999, identifier_type='MPN', value='ABC')

    @pytest.mark.unit
    def test_non_string_value_coerced(self, catalog_service):
        """A non-str value (e.g. an integer barcode) is coerced, not crashed.

        Uses a non-GTIN type so the coercion behavior is exercised without GTIN
        normalization interfering (GTIN normalization is covered separately).
        """
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(pid, identifier_type='MPN', value=12345)
        assert snap['value'] == '12345'

    @pytest.mark.unit
    def test_overlong_value_rejected_as_validation_error(self, catalog_service):
        """A value beyond the column length is a clean ValidationError, not a raw DB error."""
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(pid, identifier_type='MPN', value='x' * 256)

    @pytest.mark.unit
    def test_get_identifiers_empty_and_ordered(self, catalog_service):
        pid = catalog_service.create_product(description='widget')
        assert catalog_service.get_identifiers_for_product(pid) == []
        catalog_service.add_identifier(pid, identifier_type='MPN', value='first')
        catalog_service.add_identifier(pid, identifier_type='ASIN', value='second')
        rows = catalog_service.get_identifiers_for_product(pid)
        assert [r.value for r in rows] == ['first', 'second']

    # --- GTIN normalization / validation / lookup (Story 2.2) ------------

    @pytest.mark.unit
    def test_gtin_stored_normalized_to_14(self, catalog_service):
        """A valid UPC-A is stored (and snapshotted) as its 14-digit key."""
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type='GTIN', value='012345678905')
        assert snap['value'] == '00012345678905'
        rows = catalog_service.get_identifiers_for_product(pid)
        assert rows[0].value == '00012345678905'

    @pytest.mark.unit
    def test_gtin_cross_form_duplicate_rejected_names_product(self, catalog_service):
        """A different encoding of the same GTIN collides on the shared key."""
        from app.exceptions import ValidationError
        from sqlalchemy.exc import IntegrityError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        # A stores the GTIN-14 form; B tries the UPC-A form of the same number.
        catalog_service.add_identifier(
            pid_a, identifier_type='GTIN', value='00012345678905')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.add_identifier(
                pid_b, identifier_type='GTIN', value='012345678905')
        assert not isinstance(exc_info.value, IntegrityError)
        assert str(pid_a) in str(exc_info.value)

    @pytest.mark.unit
    def test_gtin_bad_check_digit_rejected_offers_unvalidated(self, catalog_service):
        """A bad check digit is a caught ValidationError offering GTIN_UNVALIDATED."""
        from app.exceptions import ValidationError
        from app.utils.gtin import InvalidGtinError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.add_identifier(
                pid, identifier_type='GTIN', value='012345678900')
        # Never leaks the raw pure-module error.
        assert not isinstance(exc_info.value, InvalidGtinError)
        assert 'GTIN_UNVALIDATED' in str(exc_info.value)

    @pytest.mark.unit
    def test_gtin_unvalidated_stored_as_entered(self, catalog_service):
        """GTIN_UNVALIDATED is never normalized/validated — stored verbatim."""
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type='GTIN_UNVALIDATED', value='012345678900')
        assert snap['value'] == '012345678900'
        assert snap['vendor_scope'] == ''  # global, not vendor-scoped

    @pytest.mark.unit
    def test_unvalidated_does_not_block_later_valid_gtin(self, catalog_service):
        """A quarantined value never squats a real GTIN slot on another product."""
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        # A holds the raw (check-digit-invalid) string as GTIN_UNVALIDATED...
        catalog_service.add_identifier(
            pid_a, identifier_type='GTIN_UNVALIDATED', value='012345678905')
        # ...and a valid GTIN normalizing to the same digits still persists on B.
        snap = catalog_service.add_identifier(
            pid_b, identifier_type='GTIN', value='012345678905')
        assert snap['value'] == '00012345678905'
        assert catalog_service.find_product_id_by_gtin('012345678905') == pid_b

    @pytest.mark.unit
    def test_find_product_id_by_gtin_resolves_alternate_form(self, catalog_service):
        """Any encoding resolves to the Product that owns the GTIN; misses → None."""
        pid = catalog_service.create_product(description='widget')
        catalog_service.add_identifier(
            pid, identifier_type='GTIN', value='00012345678905')
        # Looked up via the UPC-A encoding of the same number.
        assert catalog_service.find_product_id_by_gtin('012345678905') == pid
        # Unknown-but-valid GTIN and an invalid input both return None (no raise).
        assert catalog_service.find_product_id_by_gtin('00012345678929') is None
        assert catalog_service.find_product_id_by_gtin('not-a-gtin') is None
