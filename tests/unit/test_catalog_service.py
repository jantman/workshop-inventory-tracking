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


class TestOwnershipLabelText:
    """The FR12d seam (Story 2.5): ownership text is label text, never a symbol."""

    @pytest.mark.unit
    def test_returns_the_configured_text(self, catalog_service, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT',
                            'If found, return to J. Antman — 555-0100')
        assert catalog_service.ownership_label_text() == \
            'If found, return to J. Antman — 555-0100'

    @pytest.mark.unit
    @pytest.mark.parametrize('configured', [
        '',        # key present but empty in .env — config's `or ''` idiom
        '   ',     # whitespace only
        '\t\n',    # ...in any form
    ])
    def test_unset_or_blank_means_no_ownership_region_not_an_error(
            self, catalog_service, monkeypatch, configured):
        """A label with no ownership region is a valid configuration."""
        from config import Config
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', configured)
        assert catalog_service.ownership_label_text() == ''

    @pytest.mark.unit
    def test_config_reads_the_environment_variable_of_that_name(self):
        """The one piece of wiring that can silently be wrong is the env-var
        name itself: every other test here monkeypatches Config directly, so a
        typo ('LABEL_OWNER_TXT') would leave them all passing against a key that
        is never read. Asserted against config.py's source rather than by
        reloading the module — reloading rebinds config.Config to a new class
        while mariadb_catalog_service still holds the old one, which silently
        breaks every sibling test that patches the attribute. Same text-scan
        approach as the purity guards in test_gs1.py/test_gtin.py.

        Two limits, stated so nobody reads more into a pass than is there: a
        source scan cannot prove the expression is evaluated, and it matches
        wherever in the file the assignment sits. The `vars(Config)` assertion
        below covers the second — the attribute must be defined on Config
        itself, not inherited or parked on a subclass nothing reads. Quote style
        is deliberately not pinned; only the name and the idiom are."""
        import re

        import config

        assert 'LABEL_OWNER_TEXT' in vars(config.Config), \
            'LABEL_OWNER_TEXT must be defined on Config itself'

        with open(config.__file__, encoding='utf-8') as handle:
            source = handle.read()

        assert re.search(
            r"""^\s*LABEL_OWNER_TEXT\s*=\s*os\.environ\.get\(\s*"""
            r"""(['"])LABEL_OWNER_TEXT\1\s*\)\s*or\s*(['"])\2""",
            source, re.MULTILINE), \
            'Config.LABEL_OWNER_TEXT must read the env var of the same name ' \
            "via the `os.environ.get(...) or ''` idiom"

    @pytest.mark.unit
    def test_surrounding_whitespace_is_stripped(self, catalog_service, monkeypatch):
        """A '.env' value padded by an editor prints as the operator intended."""
        from config import Config
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', '  Return to: Workshop \n')
        assert catalog_service.ownership_label_text() == 'Return to: Workshop'

    @pytest.mark.unit
    def test_config_is_read_on_every_call_not_captured_at_import(
            self, catalog_service, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', 'First')
        assert catalog_service.ownership_label_text() == 'First'
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', 'Second')
        assert catalog_service.ownership_label_text() == 'Second'

    @pytest.mark.unit
    def test_the_two_label_regions_are_disjoint(self, catalog_service, monkeypatch):
        """FR12d: with ownership text configured, the element string is still
        exactly FNC1 + AI + token + id, and the text is reachable only from the
        other seam. The regions cannot bleed into one another."""
        from config import Config
        owner = 'If found, return to J. Antman — 555-0100'
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT', owner)

        payload = catalog_service.encode_internal_payload('ABC1234567')
        # Exact equality is the assertion; it already implies the text is
        # absent. Asserting substrings on top of it would add nothing but the
        # appearance of coverage — and '43' in particular is not an invariant
        # here at all, since '4' and '3' are both in the internal-id alphabet.
        assert payload == '\x1d96WITABC1234567'
        assert catalog_service.ownership_label_text() == owner

    @pytest.mark.unit
    def test_the_ownership_text_is_itself_unencodable(self, catalog_service, monkeypatch):
        """The guarantee is structural, not a convention: the very string this
        seam returns is one gs1.encode refuses, so it can never be mistaken for
        the symbol's contents."""
        from app.exceptions import ValidationError
        from config import Config
        monkeypatch.setattr(Config, 'LABEL_OWNER_TEXT',
                            'If found, return to J. Antman — 555-0100')

        text = catalog_service.ownership_label_text()
        assert text                                  # the case is non-vacuous
        with pytest.raises(ValidationError):
            catalog_service.encode_internal_payload(text)


class TestCategoryPathNormalization:
    """create_product / update_product are the sole writers of
    products.category_path, so this is where "every stored path is canonical or
    NULL" is enforced (Story 3.1, FR13, AD-4)."""

    @pytest.mark.unit
    @pytest.mark.parametrize('typed, stored', [
        ('electronics/power', 'electronics/power'),           # already canonical
        ('Electronics/Power/', 'electronics/power'),          # case + trailing
        ('/electronics//power/', 'electronics/power'),        # slash noise
        ('Electronics / Power / DC-DC', 'electronics/power/dc-dc'),  # spacing
        ('Power Supplies/DC DC', 'power supplies/dc dc'),     # intra-segment
        ('  thermal/heat-sinks  ', 'thermal/heat-sinks'),     # outer whitespace
        ('', None),                                           # blank -> NULL
        ('   ', None),                                        # whitespace -> NULL
        ('/', None),                                          # separators -> NULL
        (None, None),                                         # omitted -> NULL
    ])
    def test_create_stores_canonical(self, catalog_service, typed, stored):
        new_id = catalog_service.create_product(description='x', category_path=typed)
        assert catalog_service.get_product(new_id).category_path == stored

    @pytest.mark.unit
    @pytest.mark.parametrize('typed, stored', [
        (' /Thermal/Heat Sinks ', 'thermal/heat sinks'),      # noisy -> canonical
        ('electronics/power', 'electronics/power'),           # already canonical
        ('   ', None),                                        # blank clears
        ('', None),                                           # empty clears
    ])
    def test_update_stores_canonical(self, catalog_service, typed, stored):
        new_id = catalog_service.create_product(description='x',
                                                category_path='seed/path')
        assert catalog_service.update_product(new_id, category_path=typed) is True
        assert catalog_service.get_product(new_id).category_path == stored

    @pytest.mark.unit
    def test_update_omitting_the_field_leaves_it_unchanged(self, catalog_service):
        """An absent key means "not provided", not "clear this" (existing rule)."""
        new_id = catalog_service.create_product(description='x',
                                                category_path='Electronics/Power')
        assert catalog_service.update_product(new_id, description='y') is True
        product = catalog_service.get_product(new_id)
        assert product.description == 'y'
        assert product.category_path == 'electronics/power'

    @pytest.mark.unit
    def test_stored_value_is_idempotent_under_re_save(self, catalog_service):
        """Re-saving a product's own stored path must not change it."""
        new_id = catalog_service.create_product(description='x',
                                                category_path='Electronics/Power/')
        stored = catalog_service.get_product(new_id).category_path
        catalog_service.update_product(new_id, category_path=stored)
        assert catalog_service.get_product(new_id).category_path == stored


class TestCatalogFieldValueSuggestions:
    """The category vocabulary is the distinct set of stored category_path
    values — no node table (Story 3.1, FR14, FR15). Mirrors the inventory
    suggestion contract so one endpoint can serve both (AD-14)."""

    @pytest.fixture
    def populated(self, catalog_service):
        for path in ('Electronics/Power', 'Electronics/Power/DC-DC Converters',
                     'Thermal/Heat Sinks', 'fasteners/screws', ''):
            catalog_service.create_product(description='seed', category_path=path)
        return catalog_service

    @pytest.mark.unit
    def test_unknown_field_raises_value_error(self, catalog_service):
        with pytest.raises(ValueError):
            catalog_service.get_field_value_suggestions('vendor')

    @pytest.mark.unit
    def test_unknown_field_raises_on_normalize_too(self, catalog_service):
        with pytest.raises(ValueError):
            catalog_service.normalize_suggestion_value('vendor', 'x')

    @pytest.mark.unit
    def test_blank_query_returns_all_distinct_alphabetically(self, populated):
        result = populated.get_field_value_suggestions('category_path')
        assert result == [
            'electronics/power',
            'electronics/power/dc-dc converters',
            'fasteners/screws',
            'thermal/heat sinks',
        ]

    @pytest.mark.unit
    def test_null_and_blank_paths_never_offered(self, populated):
        result = populated.get_field_value_suggestions('category_path')
        assert None not in result
        assert '' not in result

    @pytest.mark.unit
    def test_distinct_values_only(self, catalog_service):
        for _ in range(3):
            catalog_service.create_product(description='dup',
                                           category_path='Electronics/Power')
        assert catalog_service.get_field_value_suggestions('category_path') == [
            'electronics/power']

    @pytest.mark.unit
    @pytest.mark.parametrize('query, expected', [
        ('Elec', ['electronics/power', 'electronics/power/dc-dc converters']),
        ('elec', ['electronics/power', 'electronics/power/dc-dc converters']),
        ('Electronics / Power', ['electronics/power',
                                 'electronics/power/dc-dc converters']),
        ('heat', ['thermal/heat sinks']),
        ('screws', ['fasteners/screws']),
        ('Zzz/Nope', []),
    ])
    def test_query_filters_on_the_normalized_form(self, populated, query, expected):
        assert populated.get_field_value_suggestions(
            'category_path', query=query) == expected

    @pytest.mark.unit
    def test_ranking_is_exact_then_startswith_then_contains(self, catalog_service):
        for path in ('power/supplies', 'electronics/power', 'power'):
            catalog_service.create_product(description='seed', category_path=path)
        assert catalog_service.get_field_value_suggestions(
            'category_path', query='power') == [
                'power',                # exact
                'power/supplies',       # starts-with
                'electronics/power',    # contains
            ]

    @pytest.mark.unit
    @pytest.mark.parametrize('limit, expected_len', [
        (1, 1),      # honored
        (2, 2),      # honored
        (999, 4),    # clamped to 50, then bounded by the data
        ('abc', 4),  # non-int falls back to 10, bounded by the data
        (None, 4),   # None falls back to 10 too
        (0, 1),      # clamped up to 1
        (-5, 1),     # negative clamped up to 1
    ])
    def test_limit_clamp(self, populated, limit, expected_len):
        result = populated.get_field_value_suggestions('category_path', limit=limit)
        assert len(result) == expected_len

    @pytest.mark.unit
    @pytest.mark.parametrize('kwargs, expected_len', [
        ({'limit': 999}, 50),    # clamped down to the 50 ceiling
        ({'limit': 'abc'}, 10),  # non-int falls back to the default of 10
        ({'limit': None}, 10),   # None falls back too
        ({}, 10),                # omitted -> the same default
    ])
    def test_limit_ceiling_and_default_with_a_deeper_vocabulary(
        self, catalog_service, kwargs, expected_len
    ):
        """The 50 ceiling and the 10 default need more stored paths than they
        return, or the assertion only measures the fixture.

        `test_limit_clamp` above runs against four distinct paths, so its 999,
        'abc' and None cases would pass identically with no clamp and no
        default at all. Seeding 60 paths is what makes those two numbers
        observable.
        """
        for i in range(60):
            catalog_service.create_product(description='seed',
                                           category_path=f'bulk/p{i:03d}')

        result = catalog_service.get_field_value_suggestions(
            'category_path', **kwargs)
        assert len(result) == expected_len

    @pytest.mark.unit
    def test_case_insensitive_dedup_of_pre_migration_rows(self, catalog_service):
        """Rows written before the data migration may differ only in case; the
        vocabulary must offer one of them, not both."""
        from sqlalchemy.orm import sessionmaker
        from app.database import Product

        catalog_service.create_product(description='a',
                                       category_path='electronics/power')
        second = catalog_service.create_product(description='b',
                                                category_path='seed/other')
        Session = sessionmaker(bind=catalog_service.engine)
        session = Session()
        try:
            # Write a non-canonical value directly, bypassing the service (only
            # a pre-existing row could look like this).
            session.query(Product).filter(Product.id == second).update(
                {'category_path': 'Electronics/Power'}, synchronize_session=False)
            session.commit()
        finally:
            session.close()

        result = catalog_service.get_field_value_suggestions('category_path')
        assert len(result) == 1
        assert result[0].lower() == 'electronics/power'

    @pytest.mark.unit
    def test_like_metacharacters_are_escaped(self, catalog_service):
        catalog_service.create_product(description='a', category_path='a%b')
        catalog_service.create_product(description='b', category_path='axb')
        assert catalog_service.get_field_value_suggestions(
            'category_path', query='a%b') == ['a%b']

    @pytest.mark.unit
    def test_unmatchable_query_returns_nothing_not_everything(self, populated):
        """A query the util rejects (over-length) cannot equal any stored path,
        so it matches nothing. Reading its None as 'no query' would silently
        drop the filter and hand back the whole vocabulary."""
        assert populated.get_field_value_suggestions(
            'category_path', query='a' * 600) == []

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        '/',      # separators only
        '///',    # ditto, repeated
        ' / / ',  # ditto, with whitespace
        '   ',    # whitespace only
    ])
    def test_query_carrying_no_path_means_no_filter(self, populated, query):
        """Distinct from the rejected case above: these carry no path content
        at all, so they mean the same as an omitted q — the unfiltered list."""
        assert populated.get_field_value_suggestions(
            'category_path', query=query
        ) == populated.get_field_value_suggestions('category_path')

    @pytest.mark.unit
    def test_duplicate_volume_cannot_starve_the_distinct_values(
            self, catalog_service):
        """Guards the design that replaced the DISTINCT, not DW-49 itself: it
        passed before this change too, because a fetch ceiling applied AFTER a
        SQL DISTINCT counts values. Without the DISTINCT it counts ROWS, so
        restoring the old `limit * 3 + 10` ceiling makes 100 products filed at
        `a` fill it and return `['a']` where ten distinct suggestions exist.

        Note what the 110 seeded rows can and cannot catch: a ceiling in the
        old one's range, not an arbitrarily large one. A future `.limit(10000)`
        would keep this green and still starve a bigger table — the property
        cannot be pinned by row count alone, which is why the reasoning lives
        in the read loop's comment."""
        for _ in range(100):
            catalog_service.create_product(description='dup',
                                           category_path='a')
        for letter in 'bcdefghijk':
            catalog_service.create_product(description='one',
                                           category_path=letter)

        assert catalog_service.get_field_value_suggestions(
            'category_path', limit=10) == list('abcdefghij')

    @pytest.mark.unit
    def test_the_suggestion_sql_carries_no_distinct(self, populated):
        """DW-49's mechanism, asserted the only way SQLite can show it (the
        same shape `TestTagListing` uses for `list_tags`' absent GROUP BY).

        Under MariaDB's folding collation a SQL DISTINCT collapses `café` and
        `cafe` — and any pre-migration case variant — into ONE row BEFORE the
        Python case-insensitive pass that exists to decide exactly those cases,
        so one of two genuinely distinct stored values is never offered and
        over-fetching cannot restore a row the database already dropped.
        SQLite's BINARY collation never folds, so the wrong answer is
        unreproducible here — but the ABSENCE of the DISTINCT is observable
        anywhere, and that is the whole mechanism. Without this, a later
        're-add the DISTINCT, it is cheaper' keeps the suite green and silently
        loses vocabulary in production."""
        from sqlalchemy import event

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if 'products' in statement.lower():
                statements.append(' '.join(statement.split()).upper())

        event.listen(populated.engine, 'before_cursor_execute', record)
        try:
            assert populated.get_field_value_suggestions(
                'category_path', query='elec')
            assert populated.get_field_value_suggestions('category_path')
        finally:
            event.remove(populated.engine, 'before_cursor_execute', record)

        assert statements, 'the suggestion query emitted no products SQL'
        for statement in statements:
            assert 'DISTINCT' not in statement, statement
            # GROUP BY folds under the same collation and would reintroduce
            # the identical defect while keeping the DISTINCT assertion green.
            assert 'GROUP BY' not in statement, statement

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        '\x00',      # alone: the LIKE pattern degenerates to a bare `%`
        'a\x00b',    # embedded: the pattern truncates to `%a`
        '\ud800',    # an unpaired surrogate: no UTF-8 encoding at all
        'a\ud800b',  # ...embedded
    ])
    def test_unstorable_query_answers_nothing_without_querying(
            self, populated, query):
        """DW-77: a NUL truncates the LIKE pattern at the driver, so `'\\x00'`
        would offer the ENTIRE vocabulary and `'a\\x00b'` would answer a
        different question; an unpaired surrogate cannot be bound at all and
        would raise UnicodeEncodeError out of a 200-only endpoint. Both are
        answered `[]` before the session opens, which the emitted-SQL spy
        asserts — a guard that ran after the query would still be a query."""
        from sqlalchemy import event

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(populated.engine, 'before_cursor_execute', record)
        try:
            assert populated.get_field_value_suggestions(
                'category_path', query=query) == []
        finally:
            event.remove(populated.engine, 'before_cursor_execute', record)

        assert statements == [], statements

    @pytest.mark.unit
    def test_the_two_suggestion_whitelists_are_disjoint(self):
        """The one endpoint dispatches on whitelist membership, so a name in
        both maps would silently route an item field at the products table."""
        from app.mariadb_catalog_service import FIELD_SUGGESTION_COLUMNS
        from app.mariadb_inventory_service import InventoryService
        assert not (set(FIELD_SUGGESTION_COLUMNS)
                    & set(InventoryService.FIELD_SUGGESTION_COLUMNS))

    @pytest.mark.unit
    def test_a_whitelisted_field_without_a_rule_fails_loudly(
        self, catalog_service, monkeypatch
    ):
        """Both catalog methods refuse a field that was added to the whitelist
        but given no category-specific rule.

        Unreachable while category_path is the only entry, which is exactly
        why it is pinned: the failure mode it guards is a Story 3.3 tag field
        landing in the whitelist and silently inheriting category semantics —
        echoing a non-canonical value, or leaking the whole vocabulary because
        a rejected query read as "no filter". NotImplementedError, not
        ValueError: this is a wiring error, so it must NOT become the route's
        400 "unsupported field" answer.
        """
        from app import mariadb_catalog_service as svc

        monkeypatch.setitem(svc.FIELD_SUGGESTION_COLUMNS, 'notes', 'notes')

        with pytest.raises(NotImplementedError):
            catalog_service.normalize_suggestion_value('notes', 'x')
        with pytest.raises(NotImplementedError):
            catalog_service.get_field_value_suggestions('notes', query='x')

    @pytest.mark.unit
    def test_a_child_table_field_without_a_rule_still_fails_loudly(
        self, catalog_service, monkeypatch
    ):
        """The sibling above can only stage a PRODUCT column, so it cannot see
        the failure mode the second registry introduced.

        `_FIELD_SUGGESTION_MODELS` (Story 3.3) defaults to Product, so a field
        whose column lives on a child table — as `tags` -> `tag` does — and
        that is registered in only one of the two maps resolves
        `getattr(Product, 'tag')` and raises AttributeError, which the route
        turns into a 500. The wiring error must state itself instead.
        """
        from app import mariadb_catalog_service as svc

        monkeypatch.setitem(svc.FIELD_SUGGESTION_COLUMNS, 'identifier_value',
                            'value')

        with pytest.raises(NotImplementedError):
            catalog_service.get_field_value_suggestions('identifier_value',
                                                        query='x')

    @pytest.mark.unit
    def test_every_whitelisted_field_resolves_to_a_real_column(self):
        """The two registries must agree. Nothing else checks that a field
        added to FIELD_SUGGESTION_COLUMNS from a child table also got its
        _FIELD_SUGGESTION_MODELS entry — and the whitelist is what the ONE
        endpoint dispatches on, so a mismatch is a 500 on a live field."""
        from app.database import Product
        from app.mariadb_catalog_service import (FIELD_SUGGESTION_COLUMNS,
                                                 _FIELD_SUGGESTION_MODELS)

        assert set(_FIELD_SUGGESTION_MODELS) <= set(FIELD_SUGGESTION_COLUMNS)
        for field, column_name in FIELD_SUGGESTION_COLUMNS.items():
            model = _FIELD_SUGGESTION_MODELS.get(field, Product)
            assert hasattr(model, column_name), (
                f'{field!r} maps to {model.__name__}.{column_name}, '
                f'which does not exist')

    @pytest.mark.unit
    def test_the_client_whitelist_mirrors_both_server_whitelists(self):
        """app/api_client.py's SUGGESTABLE_FIELDS documents itself as the
        union of BOTH sources behind the one endpoint (AD-13). Nothing but
        this keeps that true when either side gains or loses a field."""
        from app.api_client import SUGGESTABLE_FIELDS
        from app.mariadb_catalog_service import FIELD_SUGGESTION_COLUMNS
        from app.mariadb_inventory_service import InventoryService
        assert set(SUGGESTABLE_FIELDS) == (
            set(FIELD_SUGGESTION_COLUMNS)
            | set(InventoryService.FIELD_SUGGESTION_COLUMNS)
        )

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, expected', [
        ('Elec', 'elec'),                            # case folded
        ('Electronics/Power/', 'electronics/power'), # trailing slash dropped
        ('Zzz/Nope', 'zzz/nope'),                    # no-match still canonical
        ('', None),                                  # blank -> null
        ('   ', None),                               # whitespace -> null
        (None, None),                                # absent -> null
        ('a' * 600, None),                           # unstorable -> no create
    ])
    def test_normalize_suggestion_value(self, catalog_service, raw, expected):
        """The create affordance's source of truth: what WOULD be stored."""
        assert catalog_service.normalize_suggestion_value(
            'category_path', raw) == expected


def _rename_error(catalog_service, old_path, new_path):
    """Attempt a rename expected to be REFUSED; return the ValidationError.

    Centralizes the local `app.exceptions` import the rest of this module uses
    per-test, since every rejection row of Story 3.2's matrix needs it.
    """
    from app.exceptions import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        catalog_service.rename_category_path(old_path, new_path)
    return exc_info.value


def _paths(catalog_service, ids):
    """The stored category_path of each product id, in order."""
    return [catalog_service.get_product(pid).category_path for pid in ids]


def _force_category_path(catalog_service, product_id, value):
    """Write a raw category_path, bypassing the service's normalization.

    The only way to reproduce a legacy row carrying '' where create_product
    would have stored NULL (Story 3.1 backfilled these, but the listing must
    still exclude one if it turns up).
    """
    from app.database import Product
    session = catalog_service.Session()
    try:
        (session.query(Product).filter(Product.id == product_id)
         .update({Product.category_path: value}))
        session.commit()
    finally:
        session.close()


class TestListCategoryPaths:
    """The category tree has no node table, so its listing is the distinct set
    of assigned paths with their counts (Story 3.2, FR17)."""

    @pytest.mark.unit
    def test_empty_catalog_lists_nothing(self, catalog_service):
        assert catalog_service.list_category_paths() == []

    @pytest.mark.unit
    def test_counts_exclude_null_and_blank_paths(self, catalog_service):
        """The matrix row: a/b (x2), a (x1), one NULL and one '' row."""
        for path in ('a/b', 'a/b', 'a'):
            catalog_service.create_product(description='seed', category_path=path)
        catalog_service.create_product(description='no category')
        blank_id = catalog_service.create_product(description='legacy blank')
        _force_category_path(catalog_service, blank_id, '')

        assert catalog_service.list_category_paths() == [('a', 1), ('a/b', 2)]

    @pytest.mark.unit
    def test_paths_are_alphabetical(self, catalog_service):
        for path in ('thermal/heat', 'a/b', 'electronics/power', 'a'):
            catalog_service.create_product(description='seed', category_path=path)
        assert [path for path, _ in catalog_service.list_category_paths()] == [
            'a', 'a/b', 'electronics/power', 'thermal/heat']

    @pytest.mark.unit
    def test_the_count_is_per_exact_path_not_per_subtree(self, catalog_service):
        """Descendants are their own rows; the rename preview sums them."""
        for path in ('a', 'a/b', 'a/b/c'):
            catalog_service.create_product(description='seed', category_path=path)
        assert catalog_service.list_category_paths() == [
            ('a', 1), ('a/b', 1), ('a/b/c', 1)]


class TestCategoryRename:
    """Renaming a path carries its descendants and every product filed under
    them, atomically; a rename onto an existing node is refused rather than
    merging two branches (Story 3.2, FR17)."""

    @pytest.mark.unit
    def test_rename_carries_descendants(self, catalog_service):
        """The AC's case: electronics/power -> electronics/psu takes
        electronics/power/dc-dc with it and leaves everything else alone."""
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')
        child = catalog_service.create_product(description='converter',
                                               category_path='electronics/power/dc-dc')
        sibling = catalog_service.create_product(description='cable',
                                                 category_path='electronics/cables')
        uncategorized = catalog_service.create_product(description='misc')

        assert catalog_service.rename_category_path(
            'electronics/power', 'electronics/psu') == 2

        assert _paths(catalog_service, [node, child, sibling]) == [
            'electronics/psu', 'electronics/psu/dc-dc', 'electronics/cables']
        assert catalog_service.get_product(uncategorized).category_path is None

    @pytest.mark.unit
    def test_a_string_prefix_is_not_a_path_prefix(self, catalog_service):
        """The AC: renaming thermal/heat must not touch thermal/heatgun-parts."""
        node = catalog_service.create_product(description='sink',
                                              category_path='thermal/heat')
        near_miss = catalog_service.create_product(description='gun',
                                                   category_path='thermal/heatgun-parts')

        assert catalog_service.rename_category_path('thermal/heat',
                                                    'thermal/cooling') == 1
        assert _paths(catalog_service, [node, near_miss]) == [
            'thermal/cooling', 'thermal/heatgun-parts']

    @pytest.mark.unit
    def test_both_arguments_are_normalized(self, catalog_service):
        """The matrix row: ' /Electronics/Power/ ' -> 'Electronics / PSU'."""
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')

        assert catalog_service.rename_category_path(
            ' /Electronics/Power/ ', 'Electronics / PSU') == 1
        assert catalog_service.get_product(node).category_path == 'electronics/psu'

    @pytest.mark.unit
    def test_like_wildcards_in_a_path_are_escaped(self, catalog_service):
        """Canonical paths legitimately contain `_` and `%`, so the subtree
        LIKE must escape them — an unescaped `power\\_supplies/%` would drag
        `powerxsupplies/dc` along, and `50%/%` would drag `50off/a`."""
        node = catalog_service.create_product(description='psu',
                                              category_path='power_supplies')
        child = catalog_service.create_product(description='dc',
                                               category_path='power_supplies/dc')
        underscore_decoy = catalog_service.create_product(
            description='decoy', category_path='powerxsupplies/dc')
        percent_decoy = catalog_service.create_product(description='decoy',
                                                       category_path='50off/a')
        catalog_service.create_product(description='pct', category_path='50%/a')

        assert catalog_service.rename_category_path('power_supplies', 'psu') == 2
        assert _paths(catalog_service, [node, child, underscore_decoy]) == [
            'psu', 'psu/dc', 'powerxsupplies/dc']

        assert catalog_service.rename_category_path('50%', 'discounted') == 1
        assert catalog_service.get_product(percent_decoy).category_path == '50off/a'

    @pytest.mark.unit
    def test_destination_sharing_a_parent_is_allowed(self, catalog_service):
        """electronics/psu is a fresh node even though electronics/cables
        exists — a shared parent is not a collision."""
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')
        sibling = catalog_service.create_product(description='cable',
                                                 category_path='electronics/cables')

        assert catalog_service.rename_category_path(
            'electronics/power', 'electronics/psu') == 1
        assert _paths(catalog_service, [node, sibling]) == [
            'electronics/psu', 'electronics/cables']

    @pytest.mark.unit
    def test_rename_into_its_own_subtree_is_allowed(self, catalog_service):
        """a -> a/b is well-defined and reversible: the source subtree is
        excluded from the collision check, so it cannot block itself."""
        node = catalog_service.create_product(description='node', category_path='a')
        child = catalog_service.create_product(description='child', category_path='a/x')

        assert catalog_service.rename_category_path('a', 'a/b') == 2
        assert _paths(catalog_service, [node, child]) == ['a/b', 'a/b/x']

    @pytest.mark.unit
    def test_promote_onto_a_free_node_is_allowed(self, catalog_service):
        """a/b -> a when only the subtree lives under a."""
        child = catalog_service.create_product(description='c', category_path='a/b/c')

        assert catalog_service.rename_category_path('a/b', 'a') == 1
        assert catalog_service.get_product(child).category_path == 'a/c'

    @pytest.mark.unit
    def test_the_whole_subtree_commits_once(self, catalog_service, monkeypatch):
        """The subtree moves in ONE transaction — not a commit per row."""
        commits = []
        session_factory = catalog_service.Session

        def counting_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_commit = session.commit

            def commit():
                commits.append(1)
                return real_commit()

            session.commit = commit
            return session

        for path in ('a', 'a/b', 'a/b/c', 'a/d'):
            catalog_service.create_product(description='seed', category_path=path)
        monkeypatch.setattr(catalog_service, 'Session', counting_factory)

        assert catalog_service.rename_category_path('a', 'z') == 4
        assert commits == [1]

    # --- Rejections: every one leaves the database untouched ---------------

    @pytest.mark.unit
    def test_missing_source_is_rejected(self, catalog_service):
        other = catalog_service.create_product(description='x', category_path='a/b')

        error = _rename_error(catalog_service, 'nosuch/path', 'x')
        assert error.field == 'old_path'
        assert 'nosuch/path' in str(error)
        assert catalog_service.get_product(other).category_path == 'a/b'

    @pytest.mark.unit
    @pytest.mark.parametrize('occupied', [
        'electronics/psu',       # the destination node itself
        'electronics/psu/xyz',   # a product below the destination node
    ])
    def test_existing_destination_node_is_rejected(self, catalog_service, occupied):
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')
        blocker = catalog_service.create_product(description='other',
                                                 category_path=occupied)

        error = _rename_error(catalog_service, 'electronics/power',
                              'electronics/psu')
        assert error.field == 'new_path'
        assert 'electronics/psu' in str(error)
        assert '1 product' in str(error)
        assert _paths(catalog_service, [node, blocker]) == [
            'electronics/power', occupied]

    @pytest.mark.unit
    def test_promote_onto_an_occupied_node_is_rejected(self, catalog_service):
        """The matrix row: rows a/b/c and a/other; a/b -> a merges them."""
        child = catalog_service.create_product(description='c', category_path='a/b/c')
        blocker = catalog_service.create_product(description='o', category_path='a/other')

        error = _rename_error(catalog_service, 'a/b', 'a')
        assert error.field == 'new_path'
        assert _paths(catalog_service, [child, blocker]) == ['a/b/c', 'a/other']

    @pytest.mark.unit
    def test_no_op_rename_is_rejected(self, catalog_service):
        """Same path after normalization — nothing to do, so say so."""
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')

        error = _rename_error(catalog_service, 'electronics/power',
                              'Electronics/Power/')
        assert error.field == 'new_path'
        assert catalog_service.get_product(node).category_path == 'electronics/power'

    @pytest.mark.unit
    @pytest.mark.parametrize('old_path, new_path, field', [
        ('', 'x', 'old_path'),          # empty source
        ('   ', 'x', 'old_path'),       # whitespace source
        ('/', 'x', 'old_path'),         # separators-only source
        (None, 'x', 'old_path'),        # absent source
        ('a', '', 'new_path'),          # empty destination
        ('a', '   ', 'new_path'),       # whitespace destination
        ('a', '/', 'new_path'),         # separators-only destination
        ('a', None, 'new_path'),        # absent destination
    ])
    def test_blank_arguments_are_rejected(self, catalog_service, old_path,
                                          new_path, field):
        node = catalog_service.create_product(description='x', category_path='a')

        error = _rename_error(catalog_service, old_path, new_path)
        assert error.field == field
        assert catalog_service.get_product(node).category_path == 'a'

    @pytest.mark.unit
    @pytest.mark.parametrize('old_path, new_path, field', [
        (5, 'x', 'old_path'),                # non-string source
        ('a', ['x'], 'new_path'),            # non-string destination
        ('a' * 600, 'x', 'old_path'),        # unstorable source
        ('a', 'b' * 600, 'new_path'),        # unstorable destination
    ])
    def test_non_string_and_over_length_arguments_are_rejected(
            self, catalog_service, old_path, new_path, field):
        """A request error, not a 500: the util's InvalidCategoryPathError is
        converted rather than allowed to escape."""
        node = catalog_service.create_product(description='x', category_path='a')

        error = _rename_error(catalog_service, old_path, new_path)
        assert error.field == field
        assert catalog_service.get_product(node).category_path == 'a'

    @pytest.mark.unit
    @pytest.mark.parametrize('old_path, new_path, field', [
        ('a\x00b', 'x', 'old_path'),        # NUL in the source
        ('\x00', 'x', 'old_path'),          # ...alone
        ('a\ud800b', 'x', 'old_path'),      # unpaired surrogate in the source
        ('a', 'c\x00d', 'new_path'),        # NUL in the destination
        ('a', 'c\ud800d', 'new_path'),      # unpaired surrogate there
    ])
    def test_unstorable_arguments_are_rejected_before_anything_is_scanned(
            self, catalog_service, old_path, new_path, field):
        """DW-77 on the rename path. Normalization only strips whitespace and
        separators, so a NUL survives it into both `descendant_like_pattern`
        LIKEs — and SQLite truncates the pattern there, NARROWING both subtree
        scans. A narrowed `moving` set only produces the existing 'no products
        are filed under' rejection, but a narrowed `blockers` set is how the
        branch merge this method exists to refuse could slip through. An
        unpaired surrogate cannot be bound at all. Both are refused up front,
        naming the offending argument, with nothing written.

        The emitted-SQL spy is what makes 'before anything is scanned' an
        assertion rather than a title: field and unchanged-row checks alone
        would also hold for a guard that ran after the subtree query."""
        from sqlalchemy import event

        node = catalog_service.create_product(description='x',
                                              category_path='a')

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if 'products' in statement.lower():
                statements.append(statement)

        event.listen(catalog_service.engine, 'before_cursor_execute', record)
        try:
            error = _rename_error(catalog_service, old_path, new_path)
        finally:
            event.remove(catalog_service.engine, 'before_cursor_execute',
                         record)

        assert error.field == field
        assert statements == [], statements
        assert catalog_service.get_product(node).category_path == 'a'

    @pytest.mark.unit
    def test_a_descendant_that_would_exceed_the_column_is_rejected(
            self, catalog_service):
        """Checked for EVERY moving row before anything is written, so the
        node itself does not land while its descendant cannot."""
        deep_path = 'a/' + 'c' * 500
        node = catalog_service.create_product(description='node', category_path='a')
        child = catalog_service.create_product(description='deep',
                                               category_path=deep_path)

        error = _rename_error(catalog_service, 'a', 'b' * 500)
        assert error.field == 'new_path'
        # The offending row is NAMED. A product already past the column width
        # (Story 3.1's backfill leaves those in place) refuses every rename of
        # its branch, and a message about the destination alone sends the
        # operator hunting for a shorter path instead of for one product.
        assert f'(product {child}).' in str(error)
        assert _paths(catalog_service, [node, child]) == ['a', deep_path]

    @pytest.mark.unit
    def test_the_destination_boundary_is_a_segment_boundary_too(
            self, catalog_service):
        """The near-miss rule applies to the collision scan, not just the
        subtree scan: thermal/heatgun-parts does not occupy thermal/heat."""
        node = catalog_service.create_product(description='sink',
                                              category_path='thermal/sinks')
        near_miss = catalog_service.create_product(description='gun',
                                                   category_path='thermal/heatgun-parts')

        assert catalog_service.rename_category_path('thermal/sinks',
                                                    'thermal/heat') == 1
        assert _paths(catalog_service, [node, near_miss]) == [
            'thermal/heat', 'thermal/heatgun-parts']

    @pytest.mark.unit
    def test_wildcards_in_the_destination_are_escaped_too(self, catalog_service):
        """An unescaped `_` in the DESTINATION pattern would match any single
        character, inventing blockers out of unrelated siblings."""
        node = catalog_service.create_product(description='psu',
                                              category_path='power/source')
        decoy = catalog_service.create_product(description='decoy',
                                               category_path='dc_dc/other')

        assert catalog_service.rename_category_path('power/source',
                                                    'dc_dc/psu') == 1
        assert _paths(catalog_service, [node, decoy]) == [
            'dc_dc/psu', 'dc_dc/other']

    @pytest.mark.unit
    def test_a_blocker_sitting_at_exactly_the_destination_node(
            self, catalog_service):
        """The promote case with the parent itself occupied — the merge the
        subtree-exclusion carve-out must still refuse."""
        node = catalog_service.create_product(description='child',
                                              category_path='a/b')
        parent = catalog_service.create_product(description='parent',
                                                category_path='a')

        error = _rename_error(catalog_service, 'a/b', 'a')
        assert error.field == 'new_path'
        assert 'already exists' in str(error)
        assert _paths(catalog_service, [node, parent]) == ['a/b', 'a']

    @pytest.mark.unit
    def test_updated_at_is_bumped_on_every_moved_row(self, catalog_service):
        """Unlike the Story 3.1 data migration (which runs against a table stub
        deliberately carrying no onupdate), a rename is an ordinary ORM write
        and must leave the audit trail an edit leaves."""
        from datetime import datetime
        from app.database import Product as ProductRow

        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')
        child = catalog_service.create_product(description='converter',
                                               category_path='electronics/power/dc-dc')

        # `updated_at` defaults to func.now(), which SQLite resolves to whole
        # seconds — a rename microseconds after the insert would land in the
        # same second and make a `>` assertion pass or fail by luck. Backdating
        # first makes the bump unambiguous.
        stale = datetime(2020, 1, 1, 0, 0, 0)
        session = catalog_service.Session()
        try:
            session.query(ProductRow).update({ProductRow.updated_at: stale})
            session.commit()
        finally:
            session.close()

        catalog_service.rename_category_path('electronics/power',
                                             'electronics/psu')
        # EVERY moved row, not just the node the operator named.
        for product_id in (node, child):
            assert catalog_service.get_product(product_id).updated_at > stale

    @pytest.mark.unit
    def test_a_row_neither_predicate_claims_is_refused_not_dropped(
            self, catalog_service, monkeypatch):
        """MariaDB's case-insensitive collation can hand back a row the
        case-sensitive Python predicate then rejects. Silently dropping it
        would strand it at the old path — or, on the destination side, let
        through exactly the branch merge this method refuses. SQLite's binary
        collation cannot produce one, so the fold is simulated."""
        import app.utils.category as category_mod
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')
        stray = catalog_service.create_product(description='stray',
                                               category_path='electronics/power/x')

        real_is_descendant = category_mod.is_descendant_path

        def _case_sensitive_miss(candidate, ancestor):
            # Stand in for a stored value the collation folded onto the
            # subtree but that the predicate does not recognize.
            if candidate == 'electronics/power/x':
                return False
            return real_is_descendant(candidate, ancestor)

        monkeypatch.setattr('app.mariadb_catalog_service.category_util.is_descendant_path',
                            _case_sensitive_miss)

        error = _rename_error(catalog_service, 'electronics/power',
                              'electronics/psu')
        assert error.field == 'old_path'
        assert 'non-canonical' in str(error)
        assert str(stray) in str(error)
        assert _paths(catalog_service, [node, stray]) == [
            'electronics/power', 'electronics/power/x']

    @pytest.mark.unit
    def test_the_unclaimed_list_states_that_it_was_truncated(
            self, catalog_service, monkeypatch):
        """An operator who fixes the twenty named products and hits the same
        error again must be told the list was only ever partial."""
        import app.utils.category as category_mod
        strays = [catalog_service.create_product(
            description=f'stray {i}', category_path=f'electronics/power/x{i}')
            for i in range(25)]
        catalog_service.create_product(description='node',
                                       category_path='electronics/power')

        real_is_descendant = category_mod.is_descendant_path

        def _case_sensitive_miss(candidate, ancestor):
            if candidate.startswith('electronics/power/x'):
                return False
            return real_is_descendant(candidate, ancestor)

        monkeypatch.setattr('app.mariadb_catalog_service.category_util.is_descendant_path',
                            _case_sensitive_miss)

        error = _rename_error(catalog_service, 'electronics/power',
                              'electronics/psu')
        assert '25 in total' in str(error)
        assert str(strays[0]) in str(error)

    @pytest.mark.unit
    def test_a_failed_audit_log_cannot_mask_the_failure_it_records(
            self, catalog_service, monkeypatch):
        """The error arm's audit call must not REPLACE the exception it was
        asked to record — the caller would see 'audit sink down' instead of the
        database failure that actually killed the rename, and the real cause
        would appear nowhere at all."""
        catalog_service.create_product(description='psu',
                                       category_path='electronics/power')

        def _write_boom(*args, **kwargs):
            raise RuntimeError('the real database failure')

        def _audit_boom(*args, **kwargs):
            raise RuntimeError('audit sink down')

        # Fail inside the transaction, then fail the audit call that records it.
        monkeypatch.setattr(
            'app.mariadb_catalog_service.category_util.rewrite_category_path',
            _write_boom)
        monkeypatch.setattr('app.logging_config.log_audit_operation', _audit_boom)

        with pytest.raises(RuntimeError) as exc_info:
            catalog_service.rename_category_path('electronics/power',
                                                 'electronics/psu')
        assert 'the real database failure' in str(exc_info.value)

    @pytest.mark.unit
    def test_a_failed_audit_log_cannot_undo_a_committed_rename(
            self, catalog_service, monkeypatch):
        """Past the commit the rename HAS happened; raising here would make the
        route tell the operator to retry a rename that already succeeded."""
        node = catalog_service.create_product(description='psu',
                                              category_path='electronics/power')

        def _boom(*args, **kwargs):
            raise RuntimeError('audit sink down')

        monkeypatch.setattr('app.logging_config.log_audit_operation', _boom)

        assert catalog_service.rename_category_path(
            'electronics/power', 'electronics/psu') == 1
        assert (catalog_service.get_product(node).category_path
                == 'electronics/psu')


def _tag_error(catalog_service, product_id, tags):
    """Attempt a retag expected to be REFUSED; return the ValidationError.

    Centralizes the local `app.exceptions` import the rest of this module uses
    per-test, since every rejection row of Story 3.3's matrix needs it.
    """
    from app.exceptions import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        catalog_service.set_product_tags(product_id, tags)
    return exc_info.value


def _tag_rows(catalog_service, product_id):
    """The raw product_tags rows for a product, oldest first.

    Read through the ORM rather than get_tags_for_product where a test needs
    the row IDENTITY (the diff keeps an unchanged tag's row and its created_at,
    which a list of strings cannot show).
    """
    from app.database import ProductTag
    session = catalog_service.Session()
    try:
        return (session.query(ProductTag)
                .filter(ProductTag.product_id == product_id)
                .order_by(ProductTag.id.asc())
                .all())
    finally:
        session.close()


class TestProductTags:
    """Replace-all, diffed, idempotent tag assignment (Story 3.3, FR16)."""

    @pytest.mark.unit
    def test_assign_tags_to_an_untagged_product(self, catalog_service):
        """The matrix row: mixed case de-duplicates, the result comes back
        sorted."""
        pid = catalog_service.create_product(description='heat sink')

        assert catalog_service.set_product_tags(
            pid, ['SSR', 'ssr', 'rectifier']) == ['rectifier', 'ssr']
        assert catalog_service.get_tags_for_product(pid) == ['rectifier', 'ssr']
        assert len(_tag_rows(catalog_service, pid)) == 2

    @pytest.mark.unit
    def test_tags_are_stored_in_canonical_form(self, catalog_service):
        pid = catalog_service.create_product(description='p')

        assert catalog_service.set_product_tags(
            pid, ['  SSR  Relay ']) == ['ssr relay']
        assert catalog_service.get_tags_for_product(pid) == ['ssr relay']

    @pytest.mark.unit
    def test_the_comma_separated_form_field_is_accepted_directly(self, catalog_service):
        """The route parses the field itself, but a programmatic caller may
        hand over the raw string — both reach the same canonical list."""
        pid = catalog_service.create_product(description='p')

        assert catalog_service.set_product_tags(
            pid, ' SSR, rectifier ,, ssr ') == ['rectifier', 'ssr']

    @pytest.mark.unit
    def test_replace_all_keeps_unchanged_rows_and_diffs_the_rest(self, catalog_service):
        """The matrix row: a deleted, b KEPT (same row), c inserted."""
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['a', 'b'])
        kept_row_id = {row.tag: row.id for row in _tag_rows(catalog_service, pid)}['b']

        assert catalog_service.set_product_tags(pid, ['b', 'c']) == ['b', 'c']
        rows = {row.tag: row.id for row in _tag_rows(catalog_service, pid)}
        assert set(rows) == {'b', 'c'}
        # Diffed, not delete-all-then-insert: b's row (and its created_at)
        # survived untouched.
        assert rows['b'] == kept_row_id

    @pytest.mark.unit
    def test_re_applying_the_same_list_writes_nothing(self, catalog_service):
        """Idempotence is the route's whole retry story: saving the form again
        is always safe."""
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr', 'rectifier'])
        before = [(row.id, row.tag) for row in _tag_rows(catalog_service, pid)]

        assert catalog_service.set_product_tags(
            pid, ['ssr', 'rectifier']) == ['rectifier', 'ssr']
        assert [(row.id, row.tag)
                for row in _tag_rows(catalog_service, pid)] == before

    @pytest.mark.unit
    def test_clearing_removes_every_row(self, catalog_service):
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr', 'rectifier'])

        assert catalog_service.set_product_tags(pid, []) == []
        assert catalog_service.get_tags_for_product(pid) == []
        assert _tag_rows(catalog_service, pid) == []

    @pytest.mark.unit
    @pytest.mark.parametrize('empty', [
        [],        # an explicitly empty list
        '',        # the cleared form field
        '   ',     # whitespace only
        ',',       # a bare separator
        None,      # nothing at all
    ])
    def test_every_empty_form_clears(self, catalog_service, empty):
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])

        assert catalog_service.set_product_tags(pid, empty) == []
        assert catalog_service.get_tags_for_product(pid) == []

    @pytest.mark.unit
    def test_one_products_tags_never_touch_anothers(self, catalog_service):
        first = catalog_service.create_product(description='a')
        second = catalog_service.create_product(description='b')
        catalog_service.set_product_tags(first, ['ssr'])
        catalog_service.set_product_tags(second, ['ssr'])

        catalog_service.set_product_tags(first, [])
        assert catalog_service.get_tags_for_product(second) == ['ssr']

    @pytest.mark.unit
    def test_the_whole_replace_commits_once(self, catalog_service, monkeypatch):
        """Deletes and inserts land in ONE transaction — not a commit per row."""
        commits = []
        session_factory = catalog_service.Session

        def counting_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_commit = session.commit

            def commit():
                commits.append(1)
                return real_commit()

            session.commit = commit
            return session

        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['a', 'b', 'c'])
        monkeypatch.setattr(catalog_service, 'Session', counting_factory)

        assert catalog_service.set_product_tags(pid, ['b', 'c', 'd', 'e']) == [
            'b', 'c', 'd', 'e']
        assert commits == [1]

    @pytest.mark.unit
    def test_reading_back_an_untagged_product(self, catalog_service):
        pid = catalog_service.create_product(description='p')
        assert catalog_service.get_tags_for_product(pid) == []

    @pytest.mark.unit
    def test_reading_back_an_unknown_product(self, catalog_service):
        """A read of a product that does not exist is [] — untagged, not an
        error; nothing carries tags for it either way."""
        assert catalog_service.get_tags_for_product(999999) == []

    # --- Rejections: every one leaves the rows untouched --------------------

    @pytest.mark.unit
    def test_unknown_product_is_rejected(self, catalog_service):
        error = _tag_error(catalog_service, 999999, ['x'])
        assert error.field == 'product_id'
        assert _tag_rows(catalog_service, 999999) == []

    @pytest.mark.unit
    @pytest.mark.parametrize('tags', [
        5,                  # not a string and not iterable
        object(),           # ditto
        [5, 'ssr'],         # iterable, but carries a non-string
    ])
    def test_a_non_iterable_argument_is_a_validation_error_not_a_typeerror(
            self, catalog_service, tags):
        """The method's contract is that it raises ValidationError and nothing
        else. A bare TypeError out of the iteration would reach the route's
        generic handler as a 500 instead of a message."""
        pid = catalog_service.create_product(description='p')
        error = _tag_error(catalog_service, pid, tags)
        assert error.field == 'tags'
        assert _tag_rows(catalog_service, pid) == []

    @pytest.mark.unit
    def test_an_over_length_tag_is_rejected_and_changes_nothing(self, catalog_service):
        from app.utils.tag import MAX_TAG_LENGTH
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])

        error = _tag_error(catalog_service, pid,
                           ['rectifier', 'a' * (MAX_TAG_LENGTH + 1)])
        assert error.field == 'tags'
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    def test_a_tag_containing_the_separator_is_rejected(self, catalog_service):
        """Handed as a LIST element, so nothing splits it first — the form's
        round trip could not survive it."""
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])

        error = _tag_error(catalog_service, pid, ['a,b'])
        assert error.field == 'tags'
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    def test_too_many_tags_is_rejected_before_any_write(self, catalog_service):
        from app.utils.tag import MAX_TAGS_PER_PRODUCT
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])

        error = _tag_error(catalog_service, pid,
                           [f't{i}' for i in range(MAX_TAGS_PER_PRODUCT + 1)])
        assert error.field == 'tags'
        assert str(MAX_TAGS_PER_PRODUCT) in str(error)
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    def test_a_non_string_tag_is_rejected(self, catalog_service):
        pid = catalog_service.create_product(description='p')
        error = _tag_error(catalog_service, pid, [5])
        assert error.field == 'tags'

    @pytest.mark.unit
    def test_a_uniqueness_violation_surfaces_as_a_validation_error(
            self, catalog_service, monkeypatch):
        """A UNIQUE violation on (product_id, tag) must reach the operator as
        a sentence naming the conflict — never a raw IntegrityError or a 500.

        In production the trigger is the collation: utf8mb4_unicode_ci folds
        accents, so 'café' and 'cafe' — two DISTINCT canonical tags in Python —
        collide on the index there and not under SQLite's binary one. That
        exact folding is unreproducible here: the confirmation query compares
        with `==`, so the row it can find under SQLite is the IDENTICAL
        spelling — which is the concurrent-writer shape, and the arm this test
        therefore exercises. (The folded-spelling arm, where the row found is
        spelled differently and is named as conflicting, is MariaDB-only.)
        Either way the requirement is the same: a named ValidationError, and
        nothing of this save's own written.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = catalog_service.create_product(description='p')
        session_factory = catalog_service.Session

        def colliding_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag) for obj in session.new):
                    return real_flush(*a, **kw)
                # The index already holds an equal-under-collation row: the
                # insert is refused, and the row is there for the re-query.
                planted = session_factory()
                try:
                    planted.add(ProductTag(product_id=pid, tag='café'))
                    planted.commit()
                finally:
                    planted.close()
                raise IntegrityError('INSERT', {}, Exception('duplicate'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', colliding_factory)

        error = _tag_error(catalog_service, pid, ['café', 'ssr'])
        assert error.field == 'tags'
        assert 'café' in str(error)
        # The race is RETRYABLE — the identical list succeeds once the other
        # transaction is done — and the route reads exactly this to decide
        # whether to tell the operator to change their tags. It also carries
        # no advice of its own: the route owns the advice, and the two halves
        # contradicted each other when both wrote some.
        assert getattr(error, 'retryable', False) is True
        assert 'again' not in str(error).lower()

        monkeypatch.undo()
        # The service itself wrote nothing: its OTHER pending insert ('ssr')
        # was rolled back with the failed one, leaving only the planted row.
        assert catalog_service.get_tags_for_product(pid) == ['café']

    @pytest.mark.unit
    def test_two_new_tags_colliding_with_each_other_is_a_validation_error(
            self, catalog_service, monkeypatch):
        """The matrix's own scenario: set_product_tags(id, ['café', 'cafe']) on
        an untagged product.

        Both rows are NEW, so the rollback that precedes the conflict lookup
        removes them both and the lookup finds nothing to name — which is how
        this case escaped as a raw IntegrityError (a 500) while the
        one-committed-one-new case was handled. The product is still there, so
        the only thing the index can have refused is one requested tag against
        another.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = catalog_service.create_product(description='p')
        session_factory = catalog_service.Session

        def colliding_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag) for obj in session.new):
                    return real_flush(*a, **kw)
                # Nothing is planted: this stands in for the collation folding
                # two of the INCOMING rows onto each other.
                raise IntegrityError('INSERT', {}, Exception('duplicate'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', colliding_factory)

        error = _tag_error(catalog_service, pid, ['café', 'cafe'])
        assert error.field == 'tags'
        assert 'café' in str(error) and 'cafe' in str(error)
        assert 'Remove one' in str(error)
        # NOT retryable: the same list is refused forever, so the route must
        # ask for a different tag rather than another save.
        assert getattr(error, 'retryable', False) is False

        monkeypatch.undo()
        assert catalog_service.get_tags_for_product(pid) == []

    @pytest.mark.unit
    def test_the_collision_message_names_a_readable_number_of_tags(
            self, catalog_service, monkeypatch):
        """A collision among a PASTED list must not render a flash naming
        every tag in it.

        The arm above names the tags it cannot tell apart, which is right for
        the two-tag case it was written for — but the same branch is reached
        for a list of MAX_TAGS_PER_PRODUCT, and a Bootstrap alert naming fifty
        tags is no more actionable than one naming none.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag
        from app.mariadb_catalog_service import MAX_TAGS_NAMED_IN_ERROR
        from app.utils.tag import MAX_TAGS_PER_PRODUCT

        pid = catalog_service.create_product(description='p')
        session_factory = catalog_service.Session

        def colliding_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag) for obj in session.new):
                    return real_flush(*a, **kw)
                raise IntegrityError('INSERT', {}, Exception('duplicate'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', colliding_factory)

        requested = [f'tag{i:02d}' for i in range(MAX_TAGS_PER_PRODUCT)]
        error = _tag_error(catalog_service, pid, requested)

        message = str(error)
        named = [t for t in requested if f"'{t}'" in message]
        assert len(named) == MAX_TAGS_NAMED_IN_ERROR
        # The ones it dropped are accounted for, not silently missing.
        assert f'{MAX_TAGS_PER_PRODUCT - MAX_TAGS_NAMED_IN_ERROR} more' in message

    @pytest.mark.unit
    def test_deletes_are_flushed_before_inserts(self, catalog_service):
        """A replace must emit its DELETEs before its INSERTs.

        SQLAlchemy's unit of work orders inserts first, so replacing 'café'
        with 'cafe' would insert the new row while the old one is still
        present — a collision with a row on its way out, under MariaDB's
        accent-folding unique index. SQLite cannot reproduce the folding, but
        the statement ORDER the fix turns on is observable anywhere, and it is
        what the IntegrityError handler's conflict lookup also depends on.
        """
        from sqlalchemy import event

        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['old'])

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            verb = statement.strip().split(None, 1)[0].upper()
            if verb in ('INSERT', 'DELETE') and 'product_tags' in statement:
                statements.append(verb)

        event.listen(catalog_service.engine, 'before_cursor_execute', record)
        try:
            catalog_service.set_product_tags(pid, ['new'])
        finally:
            event.remove(catalog_service.engine, 'before_cursor_execute',
                         record)

        assert statements == ['DELETE', 'INSERT'], (
            f'expected the delete to precede the insert, got {statements}')

    @pytest.mark.unit
    @pytest.mark.parametrize('requested', [
        ['ssr'],                # one insert — nothing to collide with anyway
        ['ssr', 'rectifier'],   # two inserts — the shape that WAS mislabelled
    ])
    def test_an_integrity_error_that_is_not_a_duplicate_is_re_raised(
            self, catalog_service, monkeypatch, requested):
        """Mislabelling an FK failure as a duplicate would send the operator
        hunting for a tag conflict that does not exist — and, because a
        ValidationError is deliberately not audited, would erase a real
        operational failure from the audit log.

        The flush is failed only once ProductTag rows are pending, so the error
        lands in the guarded flush rather than in the autoflush of the
        product-existence query that precedes it.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = catalog_service.create_product(description='p')

        session_factory = catalog_service.Session

        def failing_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag) for obj in session.new):
                    return real_flush(*a, **kw)
                raise IntegrityError(
                    'INSERT', {},
                    Exception('foreign key constraint fails'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', failing_factory)

        with pytest.raises(IntegrityError):
            catalog_service.set_product_tags(pid, requested)

        monkeypatch.undo()
        assert catalog_service.get_tags_for_product(pid) == []

    @pytest.mark.unit
    def test_a_non_duplicate_failure_is_audited_as_an_error(
            self, catalog_service, monkeypatch):
        """The audit record is the only trace an operational failure leaves.

        A ValidationError skips it by design (a refused retag is not an
        operational failure), so misclassifying an infrastructure failure as one
        would lose the record entirely.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = catalog_service.create_product(description='p')
        session_factory = catalog_service.Session

        def failing_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag) for obj in session.new):
                    return real_flush(*a, **kw)
                raise IntegrityError('INSERT', {},
                                     Exception('foreign key constraint fails'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', failing_factory)

        recorded = []
        monkeypatch.setattr(
            'app.logging_config.log_audit_operation',
            lambda op, status, **kw: recorded.append((op, status)))

        with pytest.raises(IntegrityError):
            catalog_service.set_product_tags(pid, ['ssr', 'rectifier'])

        assert ('set_product_tags', 'error') in recorded

    @pytest.mark.unit
    def test_a_failed_audit_log_cannot_undo_a_committed_retag(
            self, catalog_service, monkeypatch):
        """Past the commit the tags HAVE changed; raising here would tell the
        operator to redo a write that already succeeded."""
        pid = catalog_service.create_product(description='p')

        def _boom(*args, **kwargs):
            raise RuntimeError('audit sink down')

        monkeypatch.setattr('app.logging_config.log_audit_operation', _boom)

        assert catalog_service.set_product_tags(pid, ['ssr']) == ['ssr']
        monkeypatch.undo()
        assert catalog_service.get_tags_for_product(pid) == ['ssr']


class TestListTags:
    """The tag vocabulary has no table, so its listing is the distinct set of
    assigned tags with their product counts (Story 3.3, FR16)."""

    @pytest.mark.unit
    def test_empty_catalog_lists_nothing(self, catalog_service):
        assert catalog_service.list_tags() == []

    @pytest.mark.unit
    def test_counts_products_per_tag(self, catalog_service):
        """The matrix row: 3 products, two tagged ssr, one rectifier, one
        untagged."""
        first = catalog_service.create_product(description='a')
        second = catalog_service.create_product(description='b')
        third = catalog_service.create_product(description='c')
        catalog_service.create_product(description='untagged')
        catalog_service.set_product_tags(first, ['ssr'])
        catalog_service.set_product_tags(second, ['ssr'])
        catalog_service.set_product_tags(third, ['rectifier'])

        assert catalog_service.list_tags() == [('rectifier', 1), ('ssr', 2)]

    @pytest.mark.unit
    def test_tags_are_alphabetical(self, catalog_service):
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['zener', 'ssr', 'a tag'])

        assert [tag for tag, _ in catalog_service.list_tags()] == [
            'a tag', 'ssr', 'zener']

    @pytest.mark.unit
    def test_a_tag_disappears_when_the_last_product_drops_it(self, catalog_service):
        """The vocabulary accretes purely from use — and recedes the same way."""
        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])
        assert catalog_service.list_tags() == [('ssr', 1)]

        catalog_service.set_product_tags(pid, [])
        assert catalog_service.list_tags() == []

    @pytest.mark.unit
    def test_the_counting_happens_in_python_not_in_sql(self, catalog_service):
        """SQL narrows, Python decides — the division `list_category_paths`
        states and the reason this method loops instead of grouping.

        `GROUP BY tag` under MariaDB's folding collation merges 'café' and
        'cafe' into ONE row with an arbitrary representative spelling and a
        summed count, hiding a distinct stored tag from the only page that
        exists to surface it. SQLite cannot reproduce the folding, so the
        mechanism would otherwise be untested in either direction — but the
        ABSENCE of the grouping is observable anywhere, and that is the whole
        mechanism. Without this, a later 'simplification' to func.count() keeps
        the suite green and silently loses tags in production.
        """
        from sqlalchemy import event

        pid = catalog_service.create_product(description='p')
        catalog_service.set_product_tags(pid, ['ssr'])

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if 'product_tags' in statement.lower():
                statements.append(' '.join(statement.split()).upper())

        event.listen(catalog_service.engine, 'before_cursor_execute', record)
        try:
            assert catalog_service.list_tags() == [('ssr', 1)]
        finally:
            event.remove(catalog_service.engine, 'before_cursor_execute',
                         record)

        assert statements, 'list_tags emitted no product_tags query at all'
        for statement in statements:
            assert 'GROUP BY' not in statement, statement
            assert 'COUNT(' not in statement, statement
            assert 'DISTINCT' not in statement, statement


class TestFindProductsByTag:
    """FR16's filter: exactly the tagged products, regardless of category."""

    @pytest.fixture
    def heat_sinks(self, catalog_service):
        """The acceptance scenario: three heat sinks at thermal/heat-sinks,
        two tagged ssr and one rectifier, PLUS a fourth ssr-tagged product
        filed somewhere else entirely."""
        first = catalog_service.create_product(
            description='Heat sink A', category_path='thermal/heat-sinks')
        second = catalog_service.create_product(
            description='Heat sink B', category_path='thermal/heat-sinks')
        third = catalog_service.create_product(
            description='Heat sink C', category_path='thermal/heat-sinks')
        outsider = catalog_service.create_product(
            description='Relay module', category_path='electronics/relays')
        catalog_service.set_product_tags(first, ['ssr'])
        catalog_service.set_product_tags(second, ['ssr'])
        catalog_service.set_product_tags(third, ['rectifier'])
        catalog_service.set_product_tags(outsider, ['ssr'])
        return {'first': first, 'second': second, 'third': third,
                'outsider': outsider}

    @pytest.mark.unit
    def test_the_filter_crosses_the_category_tree(self, catalog_service, heat_sinks):
        """THE acceptance criterion (FR16): the ssr products are returned
        whatever their categories, and the rectifier one is not."""
        result = catalog_service.find_products_by_tag('ssr')

        assert [p.id for p in result] == [heat_sinks['first'],
                                          heat_sinks['second'],
                                          heat_sinks['outsider']]
        assert {p.category_path for p in result} == {'thermal/heat-sinks',
                                                     'electronics/relays'}

    @pytest.mark.unit
    def test_results_are_ordered_by_description(self, catalog_service):
        pid_c = catalog_service.create_product(description='ccc')
        pid_a = catalog_service.create_product(description='aaa')
        pid_b = catalog_service.create_product(description='bbb')
        for pid in (pid_c, pid_a, pid_b):
            catalog_service.set_product_tags(pid, ['ssr'])

        assert [p.id for p in catalog_service.find_products_by_tag('ssr')] == [
            pid_a, pid_b, pid_c]

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        'ssr',           # canonical
        '  SSR ',        # padded and upper-cased
        'SSR',           # upper-cased
        ' ssr  ',        # padded
    ])
    def test_the_argument_is_normalized(self, catalog_service, heat_sinks, query):
        assert len(catalog_service.find_products_by_tag(query)) == 3

    @pytest.mark.unit
    def test_an_untagged_product_is_never_returned(self, catalog_service):
        catalog_service.create_product(description='untagged')
        assert catalog_service.find_products_by_tag('ssr') == []

    @pytest.mark.unit
    def test_an_unused_tag_returns_nothing(self, catalog_service, heat_sinks):
        """An empty result is an answer, not an error."""
        assert catalog_service.find_products_by_tag('nosuchtag') == []

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        '',              # blank
        '   ',           # whitespace only
        None,            # absent
        'a' * 200,       # over-length: no stored tag could equal it
        'a,b',           # comma-bearing: likewise unstorable
    ])
    def test_an_unusable_argument_matches_nothing_not_everything(
            self, catalog_service, heat_sinks, query):
        """Reading a rejected or empty argument as 'no filter' would hand back
        the whole catalog."""
        assert catalog_service.find_products_by_tag(query) == []

    @pytest.mark.unit
    def test_a_product_is_returned_once_even_with_other_tags(self, catalog_service):
        pid = catalog_service.create_product(description='multi')
        catalog_service.set_product_tags(pid, ['ssr', 'rectifier', 'relay'])

        assert [p.id for p in catalog_service.find_products_by_tag('ssr')] == [pid]

    @pytest.mark.unit
    def test_a_row_the_sql_matched_but_python_rejects_is_dropped(
            self, catalog_service, monkeypatch):
        """SQL narrows, Python decides — the post-query equality re-check.

        Under utf8mb4_unicode_ci the `ProductTag.tag == 'cafe'` filter ALSO
        matches a stored 'café', so the query hands back a product that does
        not carry the requested tag; returning it would put a product under a
        tag it was never given. SQLite's binary collation cannot produce that
        row, so it is staged — what the guard does with it is the same either
        way, and without this the re-check is dead code in the whole suite.
        """
        from app.database import Product

        pid = catalog_service.create_product(description='Cafe grinder')
        catalog_service.set_product_tags(pid, ['café'])
        # Baseline: with the binary collation, nothing matches 'cafe' at all.
        assert catalog_service.find_products_by_tag('cafe') == []

        real_session_factory = catalog_service.Session

        class _FoldingQuery:
            """Stands in for the query a folding collation would answer."""

            def __init__(self, rows):
                self._rows = rows

            def join(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return self._rows

        def folding_factory(*args, **kwargs):
            session = real_session_factory(*args, **kwargs)
            real_query = session.query

            def query(*entities, **kwargs_):
                if entities and entities[0] is Product:
                    product = real_query(Product).filter(
                        Product.id == pid).first()
                    # The collation folded 'café' onto the requested 'cafe'.
                    return _FoldingQuery([(product, 'café')])
                return real_query(*entities, **kwargs_)

            session.query = query
            return session

        monkeypatch.setattr(catalog_service, 'Session', folding_factory)

        assert catalog_service.find_products_by_tag('cafe') == []


class TestTagFieldValueSuggestions:
    """The tag vocabulary served through the ONE suggestions endpoint
    (Story 3.3, FR15/FR16, AD-14)."""

    @pytest.fixture
    def populated(self, catalog_service):
        pid = catalog_service.create_product(description='seed')
        catalog_service.set_product_tags(
            pid, ['ssr', 'ssr relay', 'rectifier', 'heat sink'])
        return catalog_service

    @pytest.mark.unit
    def test_blank_query_returns_all_distinct_alphabetically(self, populated):
        assert populated.get_field_value_suggestions('tags') == [
            'heat sink', 'rectifier', 'ssr', 'ssr relay']

    @pytest.mark.unit
    def test_distinct_values_only(self, catalog_service):
        """The same tag on three products is one suggestion."""
        for _ in range(3):
            pid = catalog_service.create_product(description='dup')
            catalog_service.set_product_tags(pid, ['ssr'])
        assert catalog_service.get_field_value_suggestions('tags') == ['ssr']

    @pytest.mark.unit
    def test_the_matrix_ranking_row(self, populated):
        """tags ssr / ssr relay / rectifier; a query of 'ss'."""
        assert populated.get_field_value_suggestions('tags', query='ss') == [
            'ssr', 'ssr relay']

    @pytest.mark.unit
    def test_ranking_is_exact_then_startswith_then_contains(self, catalog_service):
        pid = catalog_service.create_product(description='seed')
        catalog_service.set_product_tags(
            pid, ['relay ssr', 'ssr relay', 'ssr'])

        assert catalog_service.get_field_value_suggestions(
            'tags', query='ssr') == [
                'ssr',          # exact
                'ssr relay',    # starts-with
                'relay ssr',    # contains
            ]

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['SSR', 'ssr', '  SSR  '])
    def test_matching_is_case_insensitive_and_normalized(self, populated, query):
        assert populated.get_field_value_suggestions('tags', query=query) == [
            'ssr', 'ssr relay']

    @pytest.mark.unit
    def test_like_metacharacters_are_escaped(self, catalog_service):
        pid = catalog_service.create_product(description='seed')
        catalog_service.set_product_tags(pid, ['a%b', 'axb'])
        assert catalog_service.get_field_value_suggestions(
            'tags', query='a%b') == ['a%b']

    @pytest.mark.unit
    def test_limit_is_honored(self, populated):
        assert len(populated.get_field_value_suggestions('tags', limit=2)) == 2

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        'a' * 200,   # over-length: unstorable, therefore unmatchable
        'a,b',       # comma-bearing: likewise
    ])
    def test_an_unmatchable_query_returns_nothing_not_everything(
            self, populated, query):
        assert populated.get_field_value_suggestions('tags', query=query) == []

    @pytest.mark.unit
    @pytest.mark.parametrize('query', ['', '   ', '\t'])
    def test_a_query_carrying_no_tag_means_no_filter(self, populated, query):
        assert populated.get_field_value_suggestions(
            'tags', query=query
        ) == populated.get_field_value_suggestions('tags')

    @pytest.mark.unit
    def test_duplicate_volume_cannot_starve_the_distinct_values(
            self, catalog_service):
        """The tag half of the same guard: this passed before the change too
        (a ceiling applied after a SQL DISTINCT counts values), and fails the
        moment a row ceiling in the old one's range is restored without one —
        100 products carrying `a` fill it and hide the ten other tags behind
        it. As above, 110 rows cannot catch an arbitrarily large ceiling."""
        for _ in range(100):
            pid = catalog_service.create_product(description='dup')
            catalog_service.set_product_tags(pid, ['a'])
        for letter in 'bcdefghijk':
            pid = catalog_service.create_product(description='one')
            catalog_service.set_product_tags(pid, [letter])

        assert catalog_service.get_field_value_suggestions(
            'tags', limit=10) == list('abcdefghij')

    @pytest.mark.unit
    def test_the_suggestion_sql_carries_no_distinct(self, populated):
        """The tag vocabulary reads product_tags, so it needs its own
        assertion: a DISTINCT there folds `café` and `cafe` together under
        MariaDB's collation before the Python pass can decide between them, and
        SQLite cannot reproduce the folding — only the DISTINCT's absence."""
        from sqlalchemy import event

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if 'product_tags' in statement.lower():
                statements.append(' '.join(statement.split()).upper())

        event.listen(populated.engine, 'before_cursor_execute', record)
        try:
            assert populated.get_field_value_suggestions('tags', query='ss')
            assert populated.get_field_value_suggestions('tags')
        finally:
            event.remove(populated.engine, 'before_cursor_execute', record)

        assert statements, 'the suggestion query emitted no product_tags SQL'
        for statement in statements:
            assert 'DISTINCT' not in statement, statement
            # GROUP BY folds under the same collation and would reintroduce
            # the identical defect while keeping the DISTINCT assertion green.
            assert 'GROUP BY' not in statement, statement

    @pytest.mark.unit
    @pytest.mark.parametrize('query', [
        '\x00',      # alone: the LIKE pattern degenerates to a bare `%`
        'a\x00b',    # embedded: the pattern truncates to `%a`
        '\ud800',    # an unpaired surrogate: no UTF-8 encoding at all
        'a\ud800b',  # ...embedded
    ])
    def test_unstorable_query_answers_nothing_without_querying(
            self, populated, query):
        """DW-77 for the tag half. Distinct from the unmatchable-query row
        above: that one is refused by the tag util's own rules, this one is
        refused because the text cannot reach the database and mean what it
        says at all — and it is refused before the session opens."""
        from sqlalchemy import event

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(populated.engine, 'before_cursor_execute', record)
        try:
            assert populated.get_field_value_suggestions(
                'tags', query=query) == []
        finally:
            event.remove(populated.engine, 'before_cursor_execute', record)

        assert statements == [], statements

    @pytest.mark.unit
    @pytest.mark.parametrize('raw, expected', [
        ('SSR', 'ssr'),                    # case folded
        ('  SSR  Relay ', 'ssr relay'),    # trimmed and collapsed
        ('nosuchtag', 'nosuchtag'),        # no-match still canonical
        ('', None),                        # blank -> null
        ('   ', None),                     # whitespace -> null
        (None, None),                      # absent -> null
        ('a' * 200, None),                 # unstorable -> no create
        ('a,b', None),                     # comma-bearing -> no create
    ])
    def test_normalize_suggestion_value(self, catalog_service, raw, expected):
        """The create affordance's source of truth: what WOULD be stored."""
        assert catalog_service.normalize_suggestion_value('tags', raw) == expected

    @pytest.mark.unit
    def test_the_tag_vocabulary_is_not_the_category_vocabulary(self, catalog_service):
        """The two whitelisted catalog fields read DIFFERENT tables — a wiring
        slip that served one from the other would be invisible otherwise."""
        pid = catalog_service.create_product(description='seed',
                                             category_path='electronics/power')
        catalog_service.set_product_tags(pid, ['ssr'])

        assert catalog_service.get_field_value_suggestions('tags') == ['ssr']
        assert catalog_service.get_field_value_suggestions('category_path') == [
            'electronics/power']
