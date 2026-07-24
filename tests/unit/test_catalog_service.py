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


def _added_identifiers(catalog_service, product_id):
    """The product's identifiers EXCLUDING the derived INTERNAL row.

    Since Story 2.4 every Product created through the service also carries one
    INTERNAL identifier derived from products.internal_id. These tests are about
    identifiers the caller added, so the derived row is filtered out here (it is
    asserted on directly in TestInternalIdGeneration).
    """
    return [row for row in catalog_service.get_identifiers_for_product(product_id)
            if row.identifier_type != 'INTERNAL']


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
        # INTERNAL is deliberately absent: it is generated with the Product and
        # rejected here (Story 2.4) — see test_manual_internal_add_rejected.
    ])
    def test_add_each_type_persists(self, catalog_service, itype, value, expected):
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type=itype, value=value, vendor='Acme')
        assert snap['product_id'] == pid
        assert snap['identifier_type'] == itype
        assert snap['value'] == expected
        rows = _added_identifiers(catalog_service, pid)
        assert len(rows) == 1
        assert rows[0].identifier_type == itype
        # Unfiltered total: exactly the derived INTERNAL row plus this one. The
        # filtered helper must never be able to hide a spurious/duplicated row.
        assert len(catalog_service.get_identifiers_for_product(pid)) == 2

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
        assert _added_identifiers(catalog_service, pid) == []
        # A brand-new Product carries exactly one row overall: the derived one.
        assert len(catalog_service.get_identifiers_for_product(pid)) == 1
        catalog_service.add_identifier(pid, identifier_type='MPN', value='first')
        catalog_service.add_identifier(pid, identifier_type='ASIN', value='second')
        rows = _added_identifiers(catalog_service, pid)
        assert [r.value for r in rows] == ['first', 'second']
        assert len(catalog_service.get_identifiers_for_product(pid)) == 3

    # --- GTIN normalization / validation / lookup (Story 2.2) ------------

    @pytest.mark.unit
    def test_gtin_stored_normalized_to_14(self, catalog_service):
        """A valid UPC-A is stored (and snapshotted) as its 14-digit key."""
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type='GTIN', value='012345678905')
        assert snap['value'] == '00012345678905'
        rows = _added_identifiers(catalog_service, pid)
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


class TestRecordAmazonPurchase:
    """record_amazon_purchase: atomic Purchase-insert + ASIN-index (Story 2.3)."""

    @pytest.mark.unit
    def test_new_asin_persists_purchase_and_identifier(self, catalog_service):
        """New ASIN, first sight → one Purchase (vendor_sku==ASIN, vendor=='Amazon')
        and exactly one ASIN identifier (value==ASIN, vendor_scope=='Amazon')."""
        from decimal import Decimal
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.record_amazon_purchase(
            pid, asin='B01ABC2DEF', unit_price=Decimal('9.99'))
        assert isinstance(snap, dict)
        assert snap['product_id'] == pid
        assert snap['vendor_sku'] == 'B01ABC2DEF'
        assert snap['vendor'] == 'Amazon'

        purchases = catalog_service.get_purchases_for_product(pid)
        assert len(purchases) == 1
        assert purchases[0].vendor_sku == 'B01ABC2DEF'

        ids = _added_identifiers(catalog_service, pid)
        assert len(ids) == 1
        assert ids[0].identifier_type == 'ASIN'
        assert ids[0].value == 'B01ABC2DEF'
        assert ids[0].vendor_scope == 'Amazon'

        # Unfiltered total: the derived INTERNAL row and this ASIN, nothing
        # else — the filtered helper elsewhere must not hide a spurious row.
        all_ids = catalog_service.get_identifiers_for_product(pid)
        assert sorted(i.identifier_type for i in all_ids) == ['ASIN', 'INTERNAL']

    @pytest.mark.unit
    def test_repeat_buy_same_product_adds_purchase_not_identifier(self, catalog_service):
        """Repeat buy for the same Product → a second Purchase row, but the ASIN
        identifier count stays 1 (idempotent index)."""
        pid = catalog_service.create_product(description='widget')
        catalog_service.record_amazon_purchase(pid, asin='B01ABC2DEF')
        catalog_service.record_amazon_purchase(pid, asin='B01ABC2DEF')

        assert len(catalog_service.get_purchases_for_product(pid)) == 2
        ids = _added_identifiers(catalog_service, pid)
        assert len(ids) == 1
        assert ids[0].value == 'B01ABC2DEF'

    @pytest.mark.unit
    def test_asin_on_different_product_rejected_writes_nothing(self, catalog_service):
        """Same ASIN already on a DIFFERENT Product → ValidationError naming the
        other Product; the caller gets NO Purchase and NO identifier."""
        from app.exceptions import ValidationError
        from sqlalchemy.exc import IntegrityError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        catalog_service.record_amazon_purchase(pid_a, asin='B01ABC2DEF')

        with pytest.raises(ValidationError) as exc_info:
            catalog_service.record_amazon_purchase(pid_b, asin='B01ABC2DEF')
        # Caught domain error, NOT a raw IntegrityError...
        assert not isinstance(exc_info.value, IntegrityError)
        # ...naming the conflicting product (A).
        assert str(pid_a) in str(exc_info.value)

        # Nothing written for the caller B (no Purchase, no identifier).
        assert catalog_service.get_purchases_for_product(pid_b) == []
        assert _added_identifiers(catalog_service, pid_b) == []
        # Unfiltered: the rejected path left B with its one derived row and
        # nothing else. Asserting only on the filtered list would not notice a
        # spurious or duplicated INTERNAL row written on the way out.
        assert len(catalog_service.get_identifiers_for_product(pid_b)) == 1

    @pytest.mark.unit
    def test_unknown_product_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.record_amazon_purchase(999999, asin='B01ABC2DEF')
        assert exc_info.value.field == 'product_id'

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_asin', ['', '   ', None])
    def test_blank_or_none_asin_rejected(self, catalog_service, bad_asin):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.record_amazon_purchase(pid, asin=bad_asin)
        assert exc_info.value.field == 'asin'
        # Rejected before any write.
        assert catalog_service.get_purchases_for_product(pid) == []
        assert _added_identifiers(catalog_service, pid) == []
        # Unfiltered: still exactly the one derived row from create_product.
        assert len(catalog_service.get_identifiers_for_product(pid)) == 1

    @pytest.mark.unit
    def test_overlong_asin_rejected(self, catalog_service):
        from app.exceptions import ValidationError
        pid = catalog_service.create_product(description='widget')
        with pytest.raises(ValidationError) as exc_info:
            catalog_service.record_amazon_purchase(pid, asin='x' * 256)
        assert exc_info.value.field == 'value'

    @pytest.mark.unit
    def test_identity_independence_after_rejection(self, catalog_service):
        """After B is rejected for reusing A's ASIN, A still carries its ASIN and
        B carries none — a rejected ASIN cannot move Product identity."""
        from app.exceptions import ValidationError
        pid_a = catalog_service.create_product(description='product A')
        pid_b = catalog_service.create_product(description='product B')
        catalog_service.record_amazon_purchase(pid_a, asin='X0000ASIN1')

        with pytest.raises(ValidationError):
            catalog_service.record_amazon_purchase(pid_b, asin='X0000ASIN1')

        ids_a = _added_identifiers(catalog_service, pid_a)
        assert [(i.identifier_type, i.value) for i in ids_a] == [('ASIN', 'X0000ASIN1')]
        assert _added_identifiers(catalog_service, pid_b) == []
        # Unfiltered totals: A holds its derived row plus the ASIN, B holds only
        # its derived row. A rejected ASIN moves neither product's row count.
        assert len(catalog_service.get_identifiers_for_product(pid_a)) == 2
        assert len(catalog_service.get_identifiers_for_product(pid_b)) == 1

    @pytest.mark.unit
    def test_optional_fields_and_nondefault_vendor_pass_through(self, catalog_service):
        """All optional Purchase fields are persisted and a non-default vendor is
        stored consistently on BOTH the Purchase and the ASIN identifier scope."""
        from datetime import date
        from decimal import Decimal
        pid = catalog_service.create_product(description='widget')
        catalog_service.record_amazon_purchase(
            pid, asin='B0PASSTHRU', vendor='Amazon US',
            order_date=date(2026, 1, 2), received_date=date(2026, 1, 9),
            quantity=3, unit_price=Decimal('4.25'),
            order_number='111-2223334-5556667', source_url='https://example.test/dp/B0PASSTHRU')

        p = catalog_service.get_purchases_for_product(pid)[0]
        assert p.vendor == 'Amazon US'
        assert p.vendor_sku == 'B0PASSTHRU'
        assert p.order_date == date(2026, 1, 2)
        assert p.received_date == date(2026, 1, 9)
        assert p.quantity == 3
        assert p.unit_price == Decimal('4.25')
        assert p.order_number == '111-2223334-5556667'
        assert p.source_url == 'https://example.test/dp/B0PASSTHRU'

        ids = _added_identifiers(catalog_service, pid)
        assert len(ids) == 1
        assert ids[0].vendor_scope == 'Amazon US'  # matches Purchase.vendor


class TestInternalIdGeneration:
    """create_product as the sole internal_id writer (Story 2.4, FR12, AD-8)."""

    @staticmethod
    def _products_with(catalog_service, value):
        """Every Product row holding `value` in internal_id."""
        from app.database import Product
        session = catalog_service.Session()
        try:
            return (session.query(Product)
                    .filter(Product.internal_id == value).all())
        finally:
            session.close()

    @staticmethod
    def _internal_rows(catalog_service, value=None):
        """Every INTERNAL identifier row (optionally filtered by value)."""
        from app.database import ProductIdentifier
        session = catalog_service.Session()
        try:
            q = (session.query(ProductIdentifier)
                 .filter(ProductIdentifier.identifier_type == 'INTERNAL'))
            if value is not None:
                q = q.filter(ProductIdentifier.value == value)
            return q.all()
        finally:
            session.close()

    @staticmethod
    def _product_count(catalog_service):
        from app.database import Product
        session = catalog_service.Session()
        try:
            return session.query(Product).count()
        finally:
            session.close()

    @pytest.mark.unit
    def test_new_product_gets_valid_internal_id_and_derived_row(self, catalog_service):
        """A saved Product carries a valid internal_id and exactly one derived
        INTERNAL identifier row with the identical value and global scope."""
        from app.utils.internal_id import is_valid_internal_id

        pid = catalog_service.create_product(description='LM317')
        product = catalog_service.get_product(pid)
        assert is_valid_internal_id(product.internal_id)

        rows = [r for r in catalog_service.get_identifiers_for_product(pid)
                if r.identifier_type == 'INTERNAL']
        assert len(rows) == 1
        assert rows[0].value == product.internal_id
        assert rows[0].vendor_scope == ''   # INTERNAL is global (AD-9)

    @pytest.mark.unit
    def test_to_dict_carries_internal_id(self, catalog_service):
        pid = catalog_service.create_product(description='LM317')
        product = catalog_service.get_product(pid)
        assert product.to_dict()['internal_id'] == product.internal_id

    @pytest.mark.unit
    def test_each_product_gets_a_distinct_internal_id(self, catalog_service):
        ids = {catalog_service.get_product(
            catalog_service.create_product(description=f'w{n}')).internal_id
            for n in range(25)}
        assert len(ids) == 25

    @pytest.mark.unit
    def test_no_db_default_supplies_internal_id(self):
        """The column has no default/server_default — the service is sole writer."""
        from app.database import Product
        column = Product.__table__.columns['internal_id']
        assert column.default is None
        assert column.server_default is None
        assert column.nullable is False
        assert 'uq_products_internal_id' in {
            c.name for c in Product.__table__.constraints if c.name}

    @pytest.mark.unit
    def test_collision_retries_with_a_fresh_candidate(self, catalog_service, monkeypatch):
        """A taken candidate is retried; the Product lands on the fresh value and
        the already-stored one is neither duplicated nor orphaned."""
        first = catalog_service.create_product(description='product A')
        taken = catalog_service.get_product(first).internal_id

        candidates = iter([taken, taken, 'FRESH00001'])
        monkeypatch.setattr('app.utils.internal_id.generate_internal_id',
                            lambda **kw: next(candidates))

        second = catalog_service.create_product(description='product B')
        assert isinstance(second, int)
        assert catalog_service.get_product(second).internal_id == 'FRESH00001'

        # The colliding value is still held by exactly one Product (A) and one
        # identifier row — no duplicate, no orphan from the rolled-back attempts.
        holders = self._products_with(catalog_service, taken)
        assert [p.id for p in holders] == [first]
        assert len(self._internal_rows(catalog_service, taken)) == 1
        assert len(self._internal_rows(catalog_service, 'FRESH00001')) == 1

    @pytest.mark.unit
    def test_collision_on_the_derived_identifier_row_also_retries(self, catalog_service, monkeypatch):
        """The retry covers BOTH unique constraints: an INTERNAL identifier row
        whose value no Product holds still forces a fresh candidate."""
        from app.database import ProductIdentifier
        host = catalog_service.create_product(description='host')
        session = catalog_service.Session()
        try:
            session.add(ProductIdentifier(product_id=host, identifier_type='INTERNAL',
                                          value='SQ8ATTED91', vendor_scope=''))
            session.commit()
        finally:
            session.close()

        candidates = iter(['SQ8ATTED91', 'FRESH00002'])
        monkeypatch.setattr('app.utils.internal_id.generate_internal_id',
                            lambda **kw: next(candidates))

        pid = catalog_service.create_product(description='product B')
        assert catalog_service.get_product(pid).internal_id == 'FRESH00002'
        assert len(self._internal_rows(catalog_service, 'SQ8ATTED91')) == 1

    @pytest.mark.unit
    def test_retry_budget_exhausted_writes_nothing_and_audits_error(
            self, catalog_service, monkeypatch):
        """A generator stuck on a taken value gives up: None, nothing written,
        and the failure is audit-logged as an error."""
        import app.logging_config as logging_config
        from app.mariadb_catalog_service import INTERNAL_ID_MAX_ATTEMPTS

        first = catalog_service.create_product(description='product A')
        taken = catalog_service.get_product(first).internal_id
        before = self._product_count(catalog_service)

        calls = []
        monkeypatch.setattr('app.utils.internal_id.generate_internal_id',
                            lambda **kw: calls.append(1) or taken)
        audit = []
        monkeypatch.setattr(logging_config, 'log_audit_operation',
                            lambda op, status, **kw: audit.append((op, status)))

        assert catalog_service.create_product(description='doomed') is None
        assert ('create_product', 'error') in audit
        assert len(calls) == INTERNAL_ID_MAX_ATTEMPTS

        # Nothing landed: no extra Product, and the taken value is still single.
        assert self._product_count(catalog_service) == before
        assert len(self._internal_rows(catalog_service, taken)) == 1

    @pytest.mark.unit
    def test_foreign_integrity_error_is_reraised_not_retried(
            self, catalog_service, monkeypatch):
        """An IntegrityError that is NOT an internal-id collision is re-raised
        (surfacing as create_product's None + audit error), never mislabelled as
        a collision and never retried."""
        import app.logging_config as logging_config
        from sqlalchemy.exc import IntegrityError

        real_session_factory = catalog_service.Session
        flush_calls = []

        class _FlushAlwaysFails:
            """Proxies a real session but fails every flush with a foreign
            IntegrityError, so the candidate lookup finds nothing taken."""

            def __init__(self, session):
                self._session = session

            def __getattr__(self, name):
                return getattr(self._session, name)

            def flush(self, *args, **kwargs):
                flush_calls.append(1)
                raise IntegrityError('INSERT INTO products', {},
                                     Exception('FOREIGN KEY constraint failed'))

        monkeypatch.setattr(catalog_service, 'Session',
                            lambda: _FlushAlwaysFails(real_session_factory()))
        gen_calls = []
        monkeypatch.setattr(
            'app.utils.internal_id.generate_internal_id',
            lambda **kw: (gen_calls.append(1) or 'F0RE1GN001'))
        audit = []
        monkeypatch.setattr(logging_config, 'log_audit_operation',
                            lambda op, status, **kw: audit.append((op, status, kw)))

        assert catalog_service.create_product(description='doomed') is None
        # Exactly one attempt — a non-collision failure is not retried.
        assert flush_calls == [1]
        assert gen_calls == [1]
        op, status, kw = audit[-1]
        assert (op, status) == ('create_product', 'error')
        # The raw DB error is what surfaced, not a fabricated collision message.
        assert 'FOREIGN KEY' in kw['error_details']
        assert self._products_with(catalog_service, 'F0RE1GN001') == []

    @pytest.mark.unit
    def test_manual_internal_add_rejected(self, catalog_service):
        """add_identifier can never create or replace the derived INTERNAL row."""
        from app.exceptions import ValidationError
        from app.models import IdentifierType
        pid = catalog_service.create_product(description='widget')
        stored = self._internal_rows(catalog_service)

        with pytest.raises(ValidationError) as exc_info:
            catalog_service.add_identifier(pid, identifier_type='INTERNAL', value='X')
        assert exc_info.value.field == 'identifier_type'

        # ...and the enum member is rejected identically.
        with pytest.raises(ValidationError):
            catalog_service.add_identifier(pid, identifier_type=IdentifierType.INTERNAL,
                                           value='X')
        # Nothing written by either attempt.
        assert [(r.product_id, r.value) for r in self._internal_rows(catalog_service)] == \
               [(r.product_id, r.value) for r in stored]

    @pytest.mark.unit
    def test_update_product_cannot_change_internal_id(self, catalog_service):
        """internal_id is outside _PRODUCT_FIELDS: the update is ignored, not an error."""
        pid = catalog_service.create_product(description='widget')
        original = catalog_service.get_product(pid).internal_id

        assert catalog_service.update_product(pid, internal_id='HACKED',
                                              description='renamed') is True
        product = catalog_service.get_product(pid)
        assert product.internal_id == original
        assert product.description == 'renamed'   # the legitimate field did apply


class TestEncodeInternalPayload:
    """The AD-16 config seam: one config pair drives the whole grammar."""

    @pytest.mark.unit
    def test_encodes_with_the_configured_grammar(self, catalog_service):
        assert catalog_service.encode_internal_payload('ABC1234567') == \
            '\x1d96WITABC1234567'

    @pytest.mark.unit
    def test_token_change_flips_output_with_no_code_edit(self, catalog_service, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN', 'ZZZ')
        assert catalog_service.encode_internal_payload('ABC1234567') == \
            '\x1d96ZZZABC1234567'

    @pytest.mark.unit
    def test_ai_change_flips_output_with_no_code_edit(self, catalog_service, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', '97')
        assert catalog_service.encode_internal_payload('ABC1234567') == \
            '\x1d97WITABC1234567'

    @pytest.mark.unit
    def test_round_trips_through_decode_under_the_configured_grammar(self, catalog_service):
        from config import Config
        from app.utils import gs1

        pid = catalog_service.create_product(description='widget')
        internal_id = catalog_service.get_product(pid).internal_id
        payload = gs1.decode(catalog_service.encode_internal_payload(internal_id),
                             ai=Config.GS1_INTERNAL_AI, token=Config.GS1_INTERNAL_TOKEN)
        assert payload is not None
        assert payload.internal_id == internal_id

    @pytest.mark.unit
    def test_bad_id_surfaces_as_validationerror_not_the_pure_error(self, catalog_service):
        from app.exceptions import ValidationError
        from app.utils import gs1
        from app.utils.gs1 import InvalidGs1PayloadError
        from config import Config
        # The pure module must genuinely reject this input, or the test below
        # proves nothing about translation — it would pass just as well against
        # a service that validated the id itself and never called gs1.encode.
        with pytest.raises(InvalidGs1PayloadError) as pure_exc:
            gs1.encode('', ai=Config.GS1_INTERNAL_AI,
                       token=Config.GS1_INTERNAL_TOKEN)

        with pytest.raises(ValidationError) as exc_info:
            catalog_service.encode_internal_payload('')
        # ValidationError and InvalidGs1PayloadError are unrelated classes, so
        # an isinstance check alone can never fail. What must hold is that the
        # pure error was caught and re-raised carrying its message: the service
        # translates, it does not swallow or reword.
        assert not isinstance(exc_info.value, InvalidGs1PayloadError)
        assert str(pure_exc.value) in str(exc_info.value)
        assert exc_info.value.field == 'internal_id'
