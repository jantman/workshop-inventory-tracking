"""
Unit tests for CatalogService (catalog subsystem, Story 1.3).

Exercises product create / get / update via the SQLite test engine
(the `test_storage` fixture). Mirrors the InventoryService test approach.
"""

from decimal import Decimal

import pytest

from app.mariadb_catalog_service import CatalogService
from app.models import StockStatus
from config import Config


@pytest.fixture
def catalog_service(test_storage):
    return CatalogService(test_storage)


def _element_string(internal_id: str, *, ai: str = None, token: str = None) -> str:
    """The element string `encode_internal_payload` must produce for an id.

    Built from the CONFIGURED pair by default (AD-16), so reconfiguring
    GS1_INTERNAL_AI / GS1_INTERNAL_TOKEN moves this expectation with the code
    instead of red-building the suite — the failure mode DW-74 records.

    The FNC1 separator is the one part written out rather than derived: it is a
    fixed protocol character (the GS control, 0x1D), not a config value, and
    spelling it here keeps the expectation independent of the module under test.
    """
    ai = Config.GS1_INTERNAL_AI if ai is None else ai
    token = Config.GS1_INTERNAL_TOKEN if token is None else token
    return f'\x1d{ai}{token}{internal_id}'


def _overlong_id() -> str:
    """An id one character too long for the data field under the CONFIGURED
    token.

    The bound is on `token + internal_id` together, so a literal length is a
    hardcoded grammar wearing a different hat: `'A' * 28` overflows beside a
    three-character token and fits beside a two-character one, which is a red
    build under reconfiguration in the file DW-74 exists to clean of exactly
    that.
    """
    from app.utils.gs1 import MAX_DATA_FIELD_LENGTH

    length = MAX_DATA_FIELD_LENGTH - len(Config.GS1_INTERNAL_TOKEN) + 1
    # A token at or past the bound would drive this to zero, and `'A' * 0` is
    # the blank id — which fails for its own unrelated reason, so the overlong
    # case would go on passing while testing nothing. Such a token is already
    # an illegal deployment (the token-room rule refuses it), so this asserts
    # rather than adjusts: the caller has a bigger problem than this fixture.
    assert length > 0, (f'GS1_INTERNAL_TOKEN is {len(Config.GS1_INTERNAL_TOKEN)} '
                        f'characters, leaving no room for an id at all')
    return 'A' * length


OVERLONG_ID = _overlong_id()


def _shifted(text: str) -> str:
    """Advance every character one step within its own class.

    The building block for deriving an alternate grammar from the configured
    one instead of writing a second pair down: the result is the same length as
    the input, and — being computed — it is not a string literal at all, so it
    cannot trip the AD-16 literal guard.

    It does NOT on its own guarantee a usable alternate. A character outside
    both classes is passed through unchanged, and a shifted value can land on a
    grammar `gs1` itself refuses (`'32'` shifts to `'43'`, and no element string
    may open 43). `_alternate_half` is what turns this into a value that is both
    different and legal; call that, not this.

    A deliberate duplicate of `tests/unit/test_scan_resolution.py`'s helper
    rather than an import: importing across test modules recreates the coupling
    a previous sweep removed from `tests/e2e/`, and hoisting it into
    `tests/conftest.py` would rewrite a file this change does not cover.
    """
    out = []
    for char in text:
        if char in '0123456789':
            out.append(str((int(char) + 1) % 10))
        elif 'A' <= char.upper() <= 'Z':
            out.append(chr((ord(char.upper()) - ord('A') + 1) % 26 + ord('A')))
        else:  # pragma: no cover - the configured grammar is alphanumeric
            out.append(char)
    return ''.join(out)


def _alternate_half(which: str) -> str:
    """A different value for one half of the grammar (`'ai'` or `'token'`) that
    still builds a legal marker with the other half left as configured.

    Shifting once is not enough. With `GS1_INTERNAL_AI='32'` the derived AI is
    `'43'`, which `gs1` refuses outright (FR12d), so the flip tests below would
    raise instead of flipping — red-building on exactly the config change they
    exist to prove is supported, which is the DW-74 failure mode reappearing
    inside the fix for it.

    The shift is a permutation of each character class, so applying it
    repeatedly walks a cycle and steps off any barred point. Legality is decided
    by asking `gs1.encode` rather than by restating its rules here: a second
    copy of "no marker may open 43" would be one more thing to drift, and
    spelling `'43'` in this file would plant a literal for the AD-16 guard to
    trip over the day someone configures that token.
    """
    from app.utils import gs1

    is_ai = which == 'ai'
    assert is_ai or which == 'token', which
    configured = Config.GS1_INTERNAL_AI if is_ai else Config.GS1_INTERNAL_TOKEN
    candidate = _shifted(configured)
    for _ in range(36):
        if candidate != configured:
            ai = candidate if is_ai else Config.GS1_INTERNAL_AI
            token = Config.GS1_INTERNAL_TOKEN if is_ai else candidate
            try:
                gs1.encode('X', ai=ai, token=token)
            except gs1.InvalidGs1PayloadError:
                pass
            else:
                return candidate
        candidate = _shifted(candidate)
    raise AssertionError(f'no legal alternate {which} derivable from '
                         f'{configured!r}')


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

    @pytest.mark.unit
    def test_padded_identifier_columns_are_stored_trimmed(self, catalog_service):
        """A padded-but-NON-blank `mpn`/`manufacturer` stores trimmed (DW-7).

        `_clean` is shared, so the test above already catches a lost trim by way
        of `description` — this is not the only thing standing between the
        column and a regression, and does not claim to be. What it adds is the
        REASON the trim may not be dropped, recorded against the column the
        reason belongs to: `mpn` is a value two other modules compare against,
        `_ecia_match`'s exact lookup and `add_identifier`'s stored identifier
        rows, both of which hold the trimmed spelling. A stored `' RC0805-10K '`
        would miss a scan of the very part number it names while the free-text
        fallthrough silently succeeded, so nothing would look broken. Trimming
        `description` costs nothing if it stops; trimming this does.

        Asserted on the row read back through `get_product`, not on the dict
        handed in: the claim is about what the column holds, and a caller-side
        assertion would pass against a service that cleaned nothing.
        """
        new_id = catalog_service.create_product(
            description='RES 10K 0805 1%',
            mpn=' RC0805-10K ',
            manufacturer=' TI ',
        )
        product = catalog_service.get_product(new_id)
        assert product.mpn == 'RC0805-10K'
        assert product.manufacturer == 'TI'


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

    @pytest.mark.unit
    def test_update_trims_padded_identifier_columns(self, catalog_service):
        """The other write path onto the same two columns (DW-7).

        Pinned separately from create because they are separate code — create
        passes `_clean` per keyword to the `Product(...)` constructor, update
        reaches it through a whitelist loop with a per-key branch, so one can
        stop trimming while the other keeps going. A product edited to a padded
        part number is the likelier of the two in practice (a paste from a
        datasheet or a distributor page carries the space), and it would leave
        the row unreachable by the exact ECIA lookup that trims its candidate.
        """
        new_id = catalog_service.create_product(description='keep', mpn='OLD-1')
        assert catalog_service.update_product(
            new_id, mpn=' RC0805-10K ', manufacturer=' TI ') is True

        product = catalog_service.get_product(new_id)
        assert product.mpn == 'RC0805-10K'
        assert product.manufacturer == 'TI'


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
    def test_padded_value_is_stored_trimmed(self, catalog_service):
        """The other home of a part number, held to the same spelling (DW-7).

        `_ecia_match` answers one scanned candidate by looking in BOTH places a
        part number can live — the `products.mpn` column and an `MPN` identifier
        row — so the two write paths have to agree about what a stored value is
        or the same scan resolves differently depending on where the operator
        happened to record it. `_clean` is pinned on the column side; this is
        the identifier side of the same claim, and until now only the blank and
        non-string cases were covered here.
        """
        pid = catalog_service.create_product(description='widget')
        snap = catalog_service.add_identifier(
            pid, identifier_type='MPN', value=' RC0805-10K ')
        assert snap['value'] == 'RC0805-10K'

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
        # DW-23: the recovery hint must name something the operator can
        # actually do. "Store it as GTIN_UNVALIDATED" named no control at all —
        # there is no store-as anywhere; there is an identifier TYPE by that
        # name on the create form's `<select>`, and that is what the message
        # now points at.
        assert 'Store it as' not in str(exc_info.value)
        assert 'Add it with identifier type GTIN_UNVALIDATED' in str(exc_info.value)

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
        # The wedge no-read is refused by gtin.py, so the lookup path inherits
        # it and misses rather than resolving the all-zero key (DW-69).
        assert catalog_service.find_product_id_by_gtin('00000000') is None


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
            _element_string('ABC1234567')

    @pytest.mark.unit
    def test_token_change_flips_output_with_no_code_edit(self, catalog_service, monkeypatch):
        # Different from the configured token AND legal beside the configured
        # AI — `_alternate_half` guarantees both, so this test can neither go
        # vacuous nor go red on the derivation itself.
        alt_token = _alternate_half('token')
        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN', alt_token)
        assert catalog_service.encode_internal_payload('ABC1234567') == \
            _element_string('ABC1234567', token=alt_token)

    @pytest.mark.unit
    def test_ai_change_flips_output_with_no_code_edit(self, catalog_service, monkeypatch):
        alt_ai = _alternate_half('ai')
        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', alt_ai)
        assert catalog_service.encode_internal_payload('ABC1234567') == \
            _element_string('ABC1234567', ai=alt_ai)

    @pytest.mark.unit
    def test_round_trips_through_decode_under_the_configured_grammar(self, catalog_service):
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


class TestEncodeAttributesTheFaultToWhoeverCausedIt:
    """
    A deployment fault is never reported as bad user data (DW-39).

    Both failures arrive here as the same InvalidGs1PayloadError, but they are
    not the same kind of problem: a malformed configured grammar is an
    operator's, in a named config key, while a malformed id is the caller's.
    Reporting the first as a ValidationError put a perfectly valid id in the
    error's `value` and pointed `field` at `internal_id` — which the UI
    interpolates straight into "Please check the internal_id field", sending
    whoever reads it after the one thing that is not wrong.
    """

    @pytest.mark.unit
    def test_a_blank_ai_names_the_ai_key(self, catalog_service, monkeypatch):
        from app.exceptions import ConfigurationError

        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', '')
        with pytest.raises(ConfigurationError) as exc:
            catalog_service.encode_internal_payload('ABC1234567')
        assert exc.value.config_key == 'GS1_INTERNAL_AI'

    @pytest.mark.unit
    def test_a_padded_token_names_the_token_key(self, catalog_service, monkeypatch):
        """The .env fault that is invisible in an editor."""
        from app.exceptions import ConfigurationError

        monkeypatch.setattr(Config, 'GS1_INTERNAL_TOKEN',
                            ' ' + Config.GS1_INTERNAL_TOKEN)
        with pytest.raises(ConfigurationError) as exc:
            catalog_service.encode_internal_payload('ABC1234567')
        assert exc.value.config_key == 'GS1_INTERNAL_TOKEN'

    @pytest.mark.unit
    def test_a_barred_marker_names_the_pair_not_one_half(self, catalog_service,
                                                         monkeypatch):
        """The 43xx rule (FR12d) is checked against `ai + token` jointly, so
        neither half is individually at fault and naming one would send the
        operator to the wrong line of .env. '4311' is spelled out for the same
        reason FNC1 is: it is a fixed GS1 constant — the return-to contact AI
        the PRD addendum rejected — not this deployment's grammar."""
        from app.exceptions import ConfigurationError

        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', '4311')
        with pytest.raises(ConfigurationError) as exc:
            catalog_service.encode_internal_payload('ABC1234567')
        assert exc.value.config_key == 'GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN'

    @pytest.mark.unit
    @pytest.mark.parametrize('attr, value, config_key', [
        ('GS1_INTERNAL_AI', '', 'GS1_INTERNAL_AI'),
        ('GS1_INTERNAL_TOKEN', '', 'GS1_INTERNAL_TOKEN'),
        # The token-room rule: a token filling the whole data field leaves no
        # characters for an id. Its length is computed from the module's own
        # bound rather than spelled, so raising the bound cannot leave this
        # case quietly testing an ordinary token.
        ('GS1_INTERNAL_TOKEN', None, 'GS1_INTERNAL_TOKEN'),
        # Non-printable: the third per-half rule, the only one with no coverage
        # of its own above.
        ('GS1_INTERNAL_AI', '9\t6', 'GS1_INTERNAL_AI'),
        ('GS1_INTERNAL_AI', '4311', 'GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN'),
    ])
    def test_no_config_fault_blames_the_id_it_was_handed(
            self, catalog_service, monkeypatch, attr, value, config_key):
        """The defect itself, pinned across every grammar rule that can fire:
        whatever the config fault, the valid id that was passed in must not turn
        up as the error's subject, and the key named must be the one to change.
        """
        from app.exceptions import ConfigurationError
        from app.utils.gs1 import MAX_DATA_FIELD_LENGTH

        if value is None:  # the token-room case
            value = 'W' * MAX_DATA_FIELD_LENGTH
        monkeypatch.setattr(Config, attr, value)
        with pytest.raises(ConfigurationError) as exc:
            catalog_service.encode_internal_payload('ABC1234567')
        assert exc.value.config_key == config_key
        # Asserted against the message, which is the only place left where the
        # id could still surface. The two obvious alternatives cannot fail and
        # so prove nothing: `getattr(exc.value, 'field', None) != 'internal_id'`
        # holds because ConfigurationError has no `field` under any
        # implementation, and `'ABC1234567' not in str(exc.value.details)` holds
        # because `details` is built from `config_key` and a type tag alone and
        # the message never reaches it. (An `isinstance` check against
        # ValidationError would be the same mistake once more: it is a disjoint
        # sibling, already excluded by `pytest.raises` above.)
        assert 'ABC1234567' not in str(exc.value)

    @pytest.mark.unit
    def test_the_pure_error_is_carried_through_and_chained(
            self, catalog_service, monkeypatch):
        """The service translates the fault, it does not reword or swallow it:
        the operator still gets the pure module's own explanation, and the
        original error stays on __cause__ for the log."""
        from app.exceptions import ConfigurationError
        from app.utils import gs1
        from app.utils.gs1 import InvalidGs1PayloadError

        monkeypatch.setattr(Config, 'GS1_INTERNAL_AI', '')
        with pytest.raises(InvalidGs1PayloadError) as pure_exc:
            gs1.encode('ABC1234567', ai=Config.GS1_INTERNAL_AI,
                       token=Config.GS1_INTERNAL_TOKEN)

        with pytest.raises(ConfigurationError) as exc:
            catalog_service.encode_internal_payload('ABC1234567')
        assert str(pure_exc.value) in str(exc.value)
        assert isinstance(exc.value.__cause__, InvalidGs1PayloadError)

    @pytest.mark.unit
    @pytest.mark.parametrize('bad_id', [
        '',                     # blank
        None,                   # not a string
        'ABC 1234567',          # unencodable character
        OVERLONG_ID,            # one past what the data field can hold
    ])
    def test_a_bad_id_is_still_the_users_fault_not_a_config_error(
            self, catalog_service, bad_id):
        """The other direction, so the branch cannot be widened into swallowing
        genuine user-data faults: with the grammar untouched, each of `encode`'s
        four id rules is a ValidationError on `internal_id` exactly as before."""
        from app.exceptions import ValidationError

        with pytest.raises(ValidationError) as exc:
            catalog_service.encode_internal_payload(bad_id)
        assert exc.value.field == 'internal_id'
        assert exc.value.value == str(bad_id)


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
        assert payload == _element_string('ABC1234567')
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


def _rename_tag_error(catalog_service, old_tag, new_tag):
    """Attempt a tag rename expected to be REFUSED; return the ValidationError.

    Centralizes the local `app.exceptions` import the rest of this module uses
    per-test, since every rejection row of DW-48's matrix needs it.
    """
    from app.exceptions import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        catalog_service.rename_tag(old_tag, new_tag)
    return exc_info.value


def _tagged(catalog_service, *tags, description='p'):
    """A product carrying `tags`; returns its id."""
    product_id = catalog_service.create_product(description=description)
    if tags:
        catalog_service.set_product_tags(product_id, list(tags))
    return product_id


def _fold_the_select(monkeypatch, *spellings):
    """Make `rename_tag`'s one narrowing SELECT hand back the near-misses named
    in `spellings`, the way MariaDB's collation does and SQLite's binary one
    never can.

    `rename_tag` narrows with `or_(tag == old, tag == new)`. Under
    utf8mb4_unicode_ci that equality also matches a stored 'café' for a 'cafe'
    filter, which is the entire reason the method partitions in Python
    afterwards — and the entire thing the unit tier cannot otherwise stage. So
    the module's `or_` is replaced with one that ORs the REAL clauses plus an
    equality against each named spelling: `_fold_the_select(monkeypatch,
    'café')` says "the database considers 'café' to fold onto one of these two
    tags", and says nothing about any other row.

    Naming the spellings is what makes the stub FAITHFUL rather than merely
    wider. An always-true predicate would drag EVERY product_tags row into the
    result, so a moving product carrying any unrelated tag would land in
    `folded`, be reported as a conflict, and let the conflict tests pass
    against a partition that had nothing to do with folding — the one thing
    they exist to check. utf8mb4_unicode_ci folds case and accents, not
    'keepme' onto 'relay'.

    The rows are REAL rows from the test database rather than a stubbed query
    result, so what is under test is the partition, which is where the decision
    actually lives. The patch is undone by pytest's `monkeypatch` fixture at
    teardown; no test here needs it to outlive the call.
    """
    import app.mariadb_catalog_service as service_module
    from app.database import ProductTag

    real_or = service_module.or_

    def folding_or(*clauses):
        return real_or(*clauses,
                       *[ProductTag.tag == spelling for spelling in spellings])

    monkeypatch.setattr('app.mariadb_catalog_service.or_', folding_or)


class TestRenameTag:
    """Renaming a tag moves every carrying product and MERGES into an existing
    destination — the opposite of the category rename, because a Product
    carries many tags and the union of two tag sets is lossless (DW-48,
    FR16)."""

    @pytest.mark.unit
    def test_rename_moves_every_carrying_product(self, catalog_service):
        """The matrix's plain-rename row: three products carry 'ssr', nothing
        carries 'relay', so three rows are rewritten and none merged."""
        carriers = [_tagged(catalog_service, 'ssr') for _ in range(3)]
        untouched = _tagged(catalog_service, 'rectifier')

        assert catalog_service.rename_tag('ssr', 'relay') == (3, 0)

        for pid in carriers:
            assert catalog_service.get_tags_for_product(pid) == ['relay']
        assert catalog_service.get_tags_for_product(untouched) == ['rectifier']
        # The vocabulary followed: 'ssr' is gone because nothing carries it.
        assert dict(catalog_service.list_tags()) == {'relay': 3,
                                                     'rectifier': 1}

    @pytest.mark.unit
    def test_renaming_onto_an_existing_tag_merges(self, catalog_service):
        """The matrix's merge row: P1,P2 carry 'ssr'; P2,P3 carry 'relay'.

        P1's row is rewritten and P2's 'ssr' row is DELETED — P2 already
        carries the destination, and a second row would be the duplicate the
        unique constraint refuses. The counts distinguish the two outcomes
        because the operator can see the difference on the listing.
        """
        p1 = _tagged(catalog_service, 'ssr')
        p2 = _tagged(catalog_service, 'ssr', 'relay', 'keepme')
        p3 = _tagged(catalog_service, 'relay')

        assert catalog_service.rename_tag('ssr', 'relay') == (1, 1)

        assert catalog_service.get_tags_for_product(p1) == ['relay']
        # ONE relay row, not two — and the tag that had nothing to do with the
        # rename survived it.
        assert catalog_service.get_tags_for_product(p2) == ['keepme', 'relay']
        assert [row.tag for row in _tag_rows(catalog_service, p2)].count(
            'relay') == 1
        assert catalog_service.get_tags_for_product(p3) == ['relay']

    @pytest.mark.unit
    def test_both_arguments_are_normalized(self, catalog_service):
        """The matrix row: '  SSR ' -> ' Relay ' is 'ssr' -> 'relay'."""
        pid = _tagged(catalog_service, 'ssr')

        assert catalog_service.rename_tag('  SSR ', ' Relay ') == (1, 0)
        assert catalog_service.get_tags_for_product(pid) == ['relay']

    @pytest.mark.unit
    def test_a_merge_is_still_one_transaction(self, catalog_service,
                                              monkeypatch):
        """Deletes and rewrites land in ONE transaction — not a commit per
        row, so a failure halfway can never leave a tag half-renamed."""
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

        for _ in range(3):
            _tagged(catalog_service, 'ssr')
        _tagged(catalog_service, 'ssr', 'relay')
        monkeypatch.setattr(catalog_service, 'Session', counting_factory)

        assert catalog_service.rename_tag('ssr', 'relay') == (3, 1)
        assert commits == [1]

    @pytest.mark.unit
    def test_deletes_are_flushed_before_the_rewrites(self, catalog_service):
        """A merge must emit its DELETEs before its UPDATEs.

        SQLAlchemy's unit of work orders updates before deletes, so a product
        whose 'ssr' row is on its way out would still hold it while a SIBLING
        product's row is rewritten onto 'relay' — and under MariaDB's folding
        unique index a rewrite can collide with a row that is already leaving.
        SQLite cannot reproduce the folding, but the statement ORDER the fix
        turns on is observable anywhere.
        """
        from sqlalchemy import event

        _tagged(catalog_service, 'ssr')
        _tagged(catalog_service, 'ssr', 'relay')

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            verb = statement.strip().split(None, 1)[0].upper()
            if verb in ('UPDATE', 'DELETE') and 'product_tags' in statement:
                statements.append(verb)

        event.listen(catalog_service.engine, 'before_cursor_execute', record)
        try:
            catalog_service.rename_tag('ssr', 'relay')
        finally:
            event.remove(catalog_service.engine, 'before_cursor_execute',
                         record)

        assert statements == ['DELETE', 'UPDATE'], (
            f'expected the delete to precede the rewrite, got {statements}')

    # --- The folding collation's two shapes, staged on SQLite ---------------

    @pytest.mark.unit
    def test_a_folded_near_miss_is_not_dragged_along(self, catalog_service,
                                                     monkeypatch):
        """The matrix row: P1 carries 'café', P2 carries 'cafe'; renaming
        'cafe' moves ONLY P2.

        Membership in the moving set is exact Python equality, never what the
        SQL matched — so a row the collation folded onto the source is left
        exactly where it is rather than silently rewritten to a tag its
        product's owner never typed.
        """
        near_miss = _tagged(catalog_service, 'café')
        carrier = _tagged(catalog_service, 'cafe')
        bystander = _tagged(catalog_service, 'unrelated')
        _fold_the_select(monkeypatch, 'café')

        assert catalog_service.rename_tag('cafe', 'x') == (1, 0)

        assert catalog_service.get_tags_for_product(near_miss) == ['café']
        assert catalog_service.get_tags_for_product(carrier) == ['x']
        # 'unrelated' folds onto nothing, so the SELECT never hands it over —
        # and a tag the query never saw is a tag the rename cannot have moved.
        assert catalog_service.get_tags_for_product(bystander) == ['unrelated']

    @pytest.mark.unit
    def test_a_folded_destination_conflict_is_refused(self, catalog_service,
                                                      monkeypatch):
        """The matrix row: P1 carries 'ssr' AND 'café'; renaming 'ssr' ->
        'cafe' is refused, naming the product.

        Two tags the operator deliberately spelled differently are one row to
        the index, so the rewrite would collide with a row P1 also means to
        keep. Discarding either is the one outcome neither this method nor
        `set_product_tags` allows — and the refusal is decided BEFORE any write,
        because a rolled-back flush cannot say which products were involved.
        """
        conflicted = _tagged(catalog_service, 'ssr', 'café')
        clean = _tagged(catalog_service, 'ssr')
        _fold_the_select(monkeypatch, 'café')

        error = _rename_tag_error(catalog_service, 'ssr', 'cafe')
        assert error.field == 'new_tag'
        assert str(conflicted) in str(error)
        assert 'café' in str(error)
        # Nothing was written — not even for the product that could have moved.
        assert catalog_service.get_tags_for_product(conflicted) == ['café',
                                                                    'ssr']
        assert catalog_service.get_tags_for_product(clean) == ['ssr']

    @pytest.mark.unit
    def test_an_unrelated_tag_on_a_moving_product_is_not_a_conflict(
            self, catalog_service, monkeypatch):
        """The complement of the refusal below: a MOVING product may carry
        other tags, and carrying them is not a collision.

        Only a tag the database folds onto the destination can collide with the
        rewrite. 'keepme' folds onto nothing, so the mover is renamed and keeps
        it — while a genuine near-miss on a DIFFERENT product is handed to the
        partition in the same query and correctly ignored. Without this row,
        every conflict test above would still pass against a partition that
        refused on any second tag whatsoever.
        """
        mover = _tagged(catalog_service, 'ssr', 'keepme')
        near_miss = _tagged(catalog_service, 'café')
        _fold_the_select(monkeypatch, 'café')

        assert catalog_service.rename_tag('ssr', 'cafe') == (1, 0)

        assert catalog_service.get_tags_for_product(mover) == ['cafe', 'keepme']
        assert catalog_service.get_tags_for_product(near_miss) == ['café']

    @pytest.mark.unit
    def test_the_conflict_list_states_that_it_was_truncated(
            self, catalog_service, monkeypatch):
        """An operator who fixes the named products and hits the identical
        error again must be told the list was only ever partial.

        BOTH lists in the message are capped, so both are staged past the cap
        here: every conflicted product carries its own distinct near-miss
        spelling. A silently sliced spellings list is the same trap as a
        silently sliced id list — fix the ones on screen, hit the identical
        error, and there is nothing saying a spelling was withheld.
        """
        import re

        from app.mariadb_catalog_service import MAX_TAGS_NAMED_IN_ERROR

        spellings = [f'café{i:02d}' for i in range(MAX_TAGS_NAMED_IN_ERROR + 3)]
        conflicted = sorted(_tagged(catalog_service, 'ssr', spelling)
                            for spelling in spellings)
        _fold_the_select(monkeypatch, *spellings)

        message = str(_rename_tag_error(catalog_service, 'ssr', 'cafe'))

        # The two lists are PARSED out of the message rather than probed with
        # `str(pid) in message`: product 1's id is a substring of the "11 in
        # total" figure the truncation marker prints, so a containment check
        # counts ids the message never named and cannot pin the cap at all.
        ids, tags = re.search(
            r'product\(s\) (.*?) already carry (.*?), which the database',
            message).groups()

        named_ids, _, id_marker = ids.partition(', ... ')
        assert [int(pid) for pid in named_ids.split(', ')] == (
            conflicted[:MAX_TAGS_NAMED_IN_ERROR])
        assert id_marker == f'({len(conflicted)} in total)'

        named_tags, _, tag_marker = tags.partition(', ... ')
        assert named_tags.split(', ') == [
            f"'{spelling}'" for spelling in spellings[:MAX_TAGS_NAMED_IN_ERROR]]
        assert tag_marker == f'({len(spellings)} in total)'

    # --- Rejections: every one leaves the rows untouched --------------------

    @pytest.mark.unit
    def test_a_source_nothing_carries_is_rejected(self, catalog_service):
        pid = _tagged(catalog_service, 'ssr')

        error = _rename_tag_error(catalog_service, 'nosuchtag', 'relay')
        assert error.field == 'old_tag'
        assert 'nosuchtag' in str(error)
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    def test_a_no_op_rename_is_rejected(self, catalog_service):
        """'ssr' -> 'SSR' is the same canonical tag, so there is nothing to
        rename and no row to report having renamed."""
        pid = _tagged(catalog_service, 'ssr')

        error = _rename_tag_error(catalog_service, 'ssr', ' SSR ')
        assert error.field == 'new_tag'
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    @pytest.mark.parametrize('old_tag, new_tag, field', [
        ('', 'x', 'old_tag'),          # empty source
        ('   ', 'x', 'old_tag'),       # whitespace source
        (None, 'x', 'old_tag'),        # absent source
        ('ssr', '', 'new_tag'),        # empty destination
        ('ssr', '   ', 'new_tag'),     # whitespace destination
        ('ssr', None, 'new_tag'),      # absent destination
    ])
    def test_blank_arguments_are_rejected(self, catalog_service, old_tag,
                                          new_tag, field):
        pid = _tagged(catalog_service, 'ssr')

        error = _rename_tag_error(catalog_service, old_tag, new_tag)
        assert error.field == field
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    @pytest.mark.parametrize('old_tag, new_tag, field', [
        (5, 'x', 'old_tag'),                 # non-string source
        ('ssr', ['x'], 'new_tag'),           # non-string destination
        ('a' * 200, 'x', 'old_tag'),         # over-length source
        ('ssr', 'b' * 200, 'new_tag'),       # over-length destination
        ('a,b', 'x', 'old_tag'),             # separator in the source
        ('ssr', 'c,d', 'new_tag'),           # separator in the destination
    ])
    def test_unusable_arguments_are_rejected(self, catalog_service, old_tag,
                                             new_tag, field):
        """A request error, not a 500: the util's InvalidTagError is converted
        rather than allowed to escape."""
        pid = _tagged(catalog_service, 'ssr')

        error = _rename_tag_error(catalog_service, old_tag, new_tag)
        assert error.field == field
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    @pytest.mark.parametrize('old_tag, new_tag, field', [
        ('a\x00b', 'x', 'old_tag'),        # NUL in the source
        ('\x00', 'x', 'old_tag'),          # ...alone
        ('a\ud800b', 'x', 'old_tag'),      # unpaired surrogate in the source
        ('ssr', 'c\x00d', 'new_tag'),      # NUL in the destination
        ('ssr', 'c\ud800d', 'new_tag'),    # unpaired surrogate there
    ])
    def test_unstorable_arguments_are_rejected_before_anything_is_scanned(
            self, catalog_service, old_tag, new_tag, field):
        """Normalization lowercases and collapses whitespace, so a NUL or an
        unpaired surrogate survives it into the bound equality filter. A
        surrogate cannot be encoded at all; a NUL compares as something other
        than what it says on at least one backend, so the source would match
        nothing (reporting the wrong problem) or the destination would be
        WRITTEN in a form no later lookup could find. Both are refused up
        front, naming the offending argument, with nothing written.

        The emitted-SQL spy is what makes 'before anything is scanned' an
        assertion rather than a title: field and unchanged-row checks alone
        would also hold for a guard that ran after the SELECT.
        """
        from sqlalchemy import event

        pid = _tagged(catalog_service, 'ssr')

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            if 'product_tags' in statement.lower():
                statements.append(statement)

        event.listen(catalog_service.engine, 'before_cursor_execute', record)
        try:
            error = _rename_tag_error(catalog_service, old_tag, new_tag)
        finally:
            event.remove(catalog_service.engine, 'before_cursor_execute',
                         record)

        assert error.field == field
        assert statements == [], statements
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    # --- The IntegrityError backstop: a concurrent writer only --------------

    @pytest.mark.unit
    def test_a_concurrent_duplicate_is_refused_as_retryable(
            self, catalog_service, monkeypatch):
        """The matrix row: a racing writer commits the destination tag onto a
        moving product between the SELECT and the flush.

        Every collision this method can SEE is refused before the write, so a
        duplicate key at flush time can only be one it could not see. Nothing
        about the rename is wrong, which is why the refusal is marked
        `retryable` — the identical submission succeeds once the racing
        transaction is done, and a caller keying on the field alone would tell
        the operator to pick a different destination that was never the
        problem.
        """
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = _tagged(catalog_service, 'ssr')
        session_factory = catalog_service.Session

        def colliding_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag)
                           for obj in session.dirty):
                    return real_flush(*a, **kw)
                raise IntegrityError('UPDATE', {}, Exception('duplicate'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', colliding_factory)

        error = _rename_tag_error(catalog_service, 'ssr', 'relay')
        assert error.field == 'new_tag'
        assert 'relay' in str(error)
        assert getattr(error, 'retryable', False) is True

        monkeypatch.undo()
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    @pytest.mark.unit
    def test_an_integrity_error_that_is_not_a_duplicate_is_re_raised(
            self, catalog_service, monkeypatch):
        """Mislabelling an FK failure as a concurrent duplicate would send the
        operator to retry a rename that will fail forever — and, because a
        ValidationError is deliberately not audited, would erase a real
        operational failure from the audit log."""
        from sqlalchemy.exc import IntegrityError
        from app.database import ProductTag

        pid = _tagged(catalog_service, 'ssr')
        session_factory = catalog_service.Session

        def failing_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag)
                           for obj in session.dirty):
                    return real_flush(*a, **kw)
                raise IntegrityError('UPDATE', {},
                                     Exception('foreign key constraint fails'))

            session.flush = flush
            return session

        monkeypatch.setattr(catalog_service, 'Session', failing_factory)

        recorded = []
        monkeypatch.setattr(
            'app.logging_config.log_audit_operation',
            lambda op, status, **kw: recorded.append((op, status)))

        with pytest.raises(IntegrityError):
            catalog_service.rename_tag('ssr', 'relay')

        # The audit record is the only trace an operational failure leaves.
        assert ('rename_tag', 'error') in recorded

        monkeypatch.undo()
        assert catalog_service.get_tags_for_product(pid) == ['ssr']

    # --- Audit ---------------------------------------------------------------

    @pytest.mark.unit
    def test_a_successful_rename_records_both_counts(self, catalog_service,
                                                     monkeypatch):
        """One success record carrying both canonical forms and both counts —
        the merge is invisible in the row count alone."""
        _tagged(catalog_service, 'ssr')
        merged = _tagged(catalog_service, 'ssr', 'relay')

        recorded = []
        monkeypatch.setattr(
            'app.logging_config.log_audit_operation',
            lambda op, status, **kw: recorded.append((op, status, kw)))

        assert catalog_service.rename_tag(' SSR ', 'Relay') == (1, 1)

        assert [(op, status) for op, status, _ in recorded] == [
            ('rename_tag', 'success')]
        _, _, kwargs = recorded[0]
        # Keyed on the CANONICAL source, so the same tag's history does not
        # split by how the operator spelled it that day.
        assert kwargs['item_id'] == 'tag:ssr'
        # The merged products are named, not just counted: renaming back does
        # not undo a merge, so this list is the only record of which products
        # lost 'ssr' rather than having it rewritten.
        assert kwargs['changes'] == {'old_tag': 'ssr', 'new_tag': 'relay',
                                     'products_renamed': 1,
                                     'products_merged': 1,
                                     'merged_product_ids': [merged]}

    @pytest.mark.unit
    def test_a_rename_that_merges_nothing_records_an_empty_merge_list(
            self, catalog_service, monkeypatch):
        """No merge, no ids — the key is always present so a reader never has
        to tell "no products were merged" from "an older record that did not
        say"."""
        _tagged(catalog_service, 'ssr')

        recorded = []
        monkeypatch.setattr(
            'app.logging_config.log_audit_operation',
            lambda op, status, **kw: recorded.append((op, status, kw)))

        assert catalog_service.rename_tag('ssr', 'relay') == (1, 0)

        _, _, kwargs = recorded[0]
        assert kwargs['changes']['products_merged'] == 0
        assert kwargs['changes']['merged_product_ids'] == []

    @pytest.mark.unit
    def test_a_refused_rename_writes_no_audit_record(self, catalog_service,
                                                     monkeypatch):
        """A refused rename is ordinary validation, not an operational failure
        — auditing one would bury the real failures among operator typos."""
        _tagged(catalog_service, 'ssr')

        recorded = []
        monkeypatch.setattr(
            'app.logging_config.log_audit_operation',
            lambda op, status, **kw: recorded.append((op, status)))

        _rename_tag_error(catalog_service, 'nosuchtag', 'relay')
        _rename_tag_error(catalog_service, 'ssr', 'SSR')
        _rename_tag_error(catalog_service, '', 'relay')

        assert recorded == []

    @pytest.mark.unit
    def test_a_failed_audit_log_cannot_mask_the_failure_it_records(
            self, catalog_service, monkeypatch):
        """The error arm's audit call must not REPLACE the exception it was
        asked to record — the caller would see 'audit sink down' instead of the
        database failure that actually killed the rename, and the real cause
        would appear nowhere at all."""
        from app.database import ProductTag

        _tagged(catalog_service, 'ssr')
        session_factory = catalog_service.Session

        def failing_factory(*args, **kwargs):
            session = session_factory(*args, **kwargs)
            real_flush = session.flush

            def flush(*a, **kw):
                if not any(isinstance(obj, ProductTag)
                           for obj in session.dirty):
                    return real_flush(*a, **kw)
                raise RuntimeError('the real database failure')

            session.flush = flush
            return session

        def _audit_boom(*args, **kwargs):
            raise RuntimeError('audit sink down')

        monkeypatch.setattr(catalog_service, 'Session', failing_factory)
        monkeypatch.setattr('app.logging_config.log_audit_operation',
                            _audit_boom)

        with pytest.raises(RuntimeError) as exc_info:
            catalog_service.rename_tag('ssr', 'relay')
        assert 'the real database failure' in str(exc_info.value)

    @pytest.mark.unit
    def test_a_failed_audit_log_cannot_undo_a_committed_rename(
            self, catalog_service, monkeypatch):
        """Past the commit the rename HAS happened; raising here would make the
        route tell the operator to retry a rename that already succeeded — and
        send them to a tag that no longer exists."""
        pid = _tagged(catalog_service, 'ssr')

        def _boom(*args, **kwargs):
            raise RuntimeError('audit sink down')

        monkeypatch.setattr('app.logging_config.log_audit_operation', _boom)

        assert catalog_service.rename_tag('ssr', 'relay') == (1, 0)
        assert catalog_service.get_tags_for_product(pid) == ['relay']


# --- Story 5.1: tri-state quantity, verification stamp, product locations ----


def _stored_stamp(catalog_service, product_id):
    """The product's `quantity_verified_at`, read back through the service."""
    return catalog_service.get_product(product_id).quantity_verified_at


def _backdate_stamp(catalog_service, product_id, when):
    """Force `quantity_verified_at` to `when`, bypassing the service.

    Written directly on purpose. The service's whole contract is that it stamps
    NOW, so there is no supported way to assert a count in the past — and every
    "the stamp did NOT move" test needs a stamp old enough that a re-stamp would
    be unmistakable rather than a sub-millisecond difference.
    """
    from sqlalchemy.orm import sessionmaker
    from app.database import Product

    Session = sessionmaker(bind=catalog_service.engine)
    session = Session()
    try:
        session.query(Product).filter(Product.id == product_id).update(
            {'quantity_verified_at': when})
        session.commit()
    finally:
        session.close()
    return when


def _backdate_status_stamp(catalog_service, product_id, when):
    """Force `stock_status_at` to `when`, bypassing the service.

    The sibling of `_backdate_stamp` above and written directly for the same
    reason: the service only ever stamps NOW, so there is no supported way to
    assert a status in the past — and every "the stamp did NOT move" test needs
    a stored value old enough that a re-stamp is unmistakable rather than a
    sub-millisecond difference. `when=None` is also used deliberately, to
    manufacture the missing-stamp state the repair clause exists for.
    """
    from sqlalchemy.orm import sessionmaker
    from app.database import Product

    Session = sessionmaker(bind=catalog_service.engine)
    session = Session()
    try:
        session.query(Product).filter(Product.id == product_id).update(
            {'stock_status_at': when})
        session.commit()
    finally:
        session.close()
    return when


@pytest.mark.unit
class TestProductQuantityWriteContract:
    """The FR23/FR25 write contract, one test per row of the story's I/O matrix.

    The contract is only interesting because two columns move as one: clearing
    the count always clears the stamp, and the stamp moves only on a real
    ASSERTION — a changed number, an unchanged one the operator explicitly
    recounted, or a tracked number that somehow has no stamp. Every case below
    therefore asserts BOTH columns, not just the one it names, and every
    "unchanged" assertion compares against the exact datetime captured before
    the call: a `>=` would pass whether or not the stamp moved.
    """

    def test_a_new_product_is_untracked(self, catalog_service):
        """The default and the whole reason the column is nullable: tracking is
        opt-in per Product, so creating one commits to nothing."""
        pid = catalog_service.create_product(description='Fresh')
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_create_may_assert_a_quantity_and_is_stamped(self, catalog_service):
        pid = catalog_service.create_product(description='Counted at birth',
                                             quantity_on_hand='4')
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at is not None

    def test_the_recount_flag_is_a_no_op_on_create(self, catalog_service):
        """On a create there is nothing stored to re-confirm, so the flag
        changes nothing: a non-blank quantity stamps either way. Asserted so the
        argument's presence cannot quietly grow a meaning here."""
        with_flag = catalog_service.create_product(
            description='Flagged', quantity_on_hand='4',
            quantity_recounted=True)
        without = catalog_service.create_product(
            description='Unflagged', quantity_on_hand='4')
        for pid in (with_flag, without):
            product = catalog_service.get_product(pid)
            assert product.quantity_on_hand == 4
            assert product.quantity_verified_at is not None

    def test_create_with_a_blank_quantity_stays_untracked(self, catalog_service):
        """A blank string is what an untouched form field submits, so it has to
        mean the same thing as an omitted argument — not `0`."""
        pid = catalog_service.create_product(description='Blank field',
                                             quantity_on_hand='')
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_asserting_zero_is_tracked_not_cleared(self, catalog_service):
        """The distinction the whole story exists for: `0` is a COUNT."""
        pid = catalog_service.create_product(description='Empty bin')
        assert catalog_service.update_product(pid, quantity_on_hand='0') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 0
        assert product.quantity_verified_at is not None

    def test_asserting_n_stores_and_stamps(self, catalog_service):
        pid = catalog_service.create_product(description='Stocked')
        assert catalog_service.update_product(pid, quantity_on_hand='4') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at is not None

    def test_an_integer_argument_is_accepted_too(self, catalog_service):
        """The route hands strings, but the service is a service: a caller that
        already has an int must not have to stringify it to be understood — and
        the comparison against the stored INT must still see them as equal."""
        pid = catalog_service.create_product(description='Typed')
        assert catalog_service.update_product(pid, quantity_on_hand=7) is True
        assert catalog_service.get_product(pid).quantity_on_hand == 7

    def test_reasserting_the_same_value_without_the_flag_leaves_the_stamp(
            self, catalog_service):
        """THE defect this rule exists to prevent, at the service boundary.

        The edit form renders `quantity_on_hand` pre-filled, so every browser
        save re-posts it. If key presence were the trigger, fixing a typo in the
        description would re-date a count taken three months ago — destroying
        exactly the staleness signal FR25 asks to be surfaced rather than
        silently corrected. Compared for EQUALITY against the stored value
        captured first; `>=` would pass either way and could not fail.
        """
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Recounted',
                                             quantity_on_hand='4')
        old = _backdate_stamp(catalog_service, pid,
                              datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(pid, quantity_on_hand='4') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == old

    def test_an_unrelated_field_edit_leaves_the_stamp(self, catalog_service):
        """The same rule from the other direction: a description change that
        carries the pre-filled quantity along with it is still not a count."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Typo',
                                             quantity_on_hand='4')
        old = _backdate_stamp(catalog_service, pid,
                              datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, description='Typo fixed', quantity_on_hand='4') is True
        product = catalog_service.get_product(pid)
        assert product.description == 'Typo fixed'
        assert product.quantity_verified_at == old

    def test_reasserting_the_same_value_with_the_flag_moves_the_stamp(
            self, catalog_service):
        """The case a value comparison cannot see: the operator counted again
        and got the same number. Without this the recount would be unrecordable
        and the age would keep climbing on a count that was just taken."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Recounted',
                                             quantity_on_hand='4')
        old = _backdate_stamp(catalog_service, pid,
                              datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, quantity_on_hand='4', quantity_recounted=True) is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at > old

    @pytest.mark.parametrize('recounted', [False, True],
                             ids=['no_flag', 'with_flag'])
    def test_a_changed_value_always_moves_the_stamp(self, catalog_service,
                                                    recounted):
        """A different number is an assertion on its own terms — the flag is
        irrelevant to it, in either position."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Changed',
                                             quantity_on_hand='4')
        old = _backdate_stamp(catalog_service, pid,
                              datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, quantity_on_hand='5',
            quantity_recounted=recounted) is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 5
        assert product.quantity_verified_at > old

    def test_a_blank_quantity_clears_both_columns(self, catalog_service):
        """Untracking. The stamp must go with the count — an age displayed
        beside no number is an assertion about a count nobody made."""
        pid = catalog_service.create_product(description='Untrack me',
                                             quantity_on_hand='4')
        assert _stored_stamp(catalog_service, pid) is not None
        assert catalog_service.update_product(pid, quantity_on_hand='') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_the_flag_is_ignored_on_a_blank_quantity(self, catalog_service):
        """A recount that finds the product untracked is an UNTRACK, not a
        verification: both columns go to NULL and no stamp is written."""
        pid = catalog_service.create_product(description='Untrack me anyway',
                                             quantity_on_hand='4')
        assert catalog_service.update_product(
            pid, quantity_on_hand='', quantity_recounted=True) is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_the_flag_alone_with_no_quantity_key_changes_nothing(
            self, catalog_service):
        """The flag asserts nothing by itself: with no `quantity_on_hand` key in
        the update there is no submitted count to interpret, so the
        partial-update rule applies untouched."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Flag alone',
                                             quantity_on_hand='4')
        old = _backdate_stamp(catalog_service, pid,
                              datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, description='Flag alone', quantity_recounted=True) is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == old

    def test_a_missing_stamp_on_a_tracked_quantity_is_repaired(
            self, catalog_service):
        """A state this write contract otherwise makes impossible — a count with
        no record of when it was taken. Re-asserting the same number repairs it
        rather than leaving a tracked quantity permanently ageless, which would
        otherwise render as a count with no staleness at all."""
        pid = catalog_service.create_product(description='Ageless',
                                             quantity_on_hand='4')
        _backdate_stamp(catalog_service, pid, None)
        assert _stored_stamp(catalog_service, pid) is None

        assert catalog_service.update_product(pid, quantity_on_hand='4') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at is not None

    def test_a_none_quantity_clears_both_columns(self, catalog_service):
        """Same rule for a caller that passes None rather than ''. The KEY's
        presence is what says "clear"; the value only says what to clear to."""
        pid = catalog_service.create_product(description='Untrack me too',
                                             quantity_on_hand='4')
        assert catalog_service.update_product(pid, quantity_on_hand=None) is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand is None
        assert product.quantity_verified_at is None

    def test_an_absent_key_leaves_both_columns_alone(self, catalog_service):
        """The partial-update rule, unchanged: an update that never mentions the
        quantity must not untrack a product, and must not refresh its stamp
        either — nobody counted anything."""
        pid = catalog_service.create_product(description='Untouched',
                                             quantity_on_hand='4')
        stamp = _stored_stamp(catalog_service, pid)
        assert catalog_service.update_product(pid, description='Renamed') is True
        product = catalog_service.get_product(pid)
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_quantity_recounted_is_not_a_product_field(self, catalog_service):
        """It is a per-request flag, not a column and not an accepted field.

        Named in `_PRODUCT_FIELDS` it would be `setattr`-ed onto the Product and
        blow up (or, worse, be persisted); reachable through `**fields` it would
        be a caller-settable column by another name.
        """
        from app.mariadb_catalog_service import _PRODUCT_FIELDS
        from app.database import Product

        assert 'quantity_recounted' not in _PRODUCT_FIELDS
        assert 'quantity_recounted' not in Product.__table__.columns.keys()

    def test_quantity_verified_at_is_not_accepted_from_a_caller(
            self, catalog_service):
        """It is DERIVED from the act of asserting a count, never supplied.

        A caller able to set it could claim a count was verified at a time no
        count was taken — precisely the lie the age display exists to prevent —
        so the name is absent from `_PRODUCT_FIELDS` and is dropped in silence,
        exactly as `internal_id` is.
        """
        from datetime import datetime

        pid = catalog_service.create_product(description='No backdating',
                                             quantity_on_hand='4')
        stamp = _stored_stamp(catalog_service, pid)
        assert catalog_service.update_product(
            pid, quantity_verified_at=datetime(1999, 1, 1)) is True
        assert _stored_stamp(catalog_service, pid) == stamp

    def test_the_quantity_pair_is_recorded_in_the_audit_snapshot(
            self, catalog_service, monkeypatch):
        """`to_dict()` is what the audit log stores, so a column missing from it
        is a column whose history cannot be read back."""
        records = []

        def _capture(operation, status, **kwargs):
            records.append((operation, status, kwargs.get('item_after')))

        monkeypatch.setattr('app.logging_config.log_audit_operation', _capture)

        pid = catalog_service.create_product(description='Audited',
                                             quantity_on_hand='0')
        assert records[-1][0] == 'create_product'
        assert records[-1][2]['quantity_on_hand'] == 0
        assert records[-1][2]['quantity_verified_at'] is not None

    @pytest.mark.parametrize('bad', [2.9, Decimal('2.9'), True, -5,
                                     2147483648, '-5', 'abc'],
                             ids=['float', 'decimal', 'bool', 'negative-int',
                                  'over-int32', 'negative-string',
                                  'not-a-number'])
    def test_a_value_the_column_cannot_hold_is_refused_not_truncated(
            self, catalog_service, bad):
        """The service's own contract, distinct from the form rule.

        `int()` alone honours neither the type nor the bounds: it turns 2.9 into
        2 and True into 1, so an accidental float or boolean from a
        non-form caller would store a silently WRONG count and — worse — stamp
        it as freshly verified, which is precisely the lie FR25's age display
        exists to prevent. Refused instead, which `update_product` reports as
        False, and the stored state is untouched.
        """
        pid = catalog_service.create_product(description='Guarded',
                                             quantity_on_hand='4')
        before = catalog_service.get_product(pid)

        assert catalog_service.update_product(
            pid, quantity_on_hand=bad) is False

        after = catalog_service.get_product(pid)
        assert after.quantity_on_hand == before.quantity_on_hand == 4
        assert after.quantity_verified_at == before.quantity_verified_at

    def test_a_zero_padded_string_is_the_magnitude_it_names(
            self, catalog_service):
        """`int()` is not total over digit strings — CPython refuses one longer
        than 4300 digits — and the form rule bounds the MAGNITUDE, so a padded
        string is valid input that must not die here."""
        pid = catalog_service.create_product(description='Padded',
                                             quantity_on_hand='0' * 5000 + '4')
        assert catalog_service.get_product(pid).quantity_on_hand == 4

        assert catalog_service.update_product(
            pid, quantity_on_hand='0' * 5000) is True
        assert catalog_service.get_product(pid).quantity_on_hand == 0


# --- Story 5.2: the reorder threshold's write contract ----------------------


@pytest.mark.unit
class TestProductReorderThresholdWriteContract:
    """FR26's stored half: one nullable integer, written like any other field
    except that it must not go through `_clean`.

    The threshold has no second column and no stamp, so what is interesting here
    is narrower than the quantity's contract — but it is interesting in the same
    two places. `0` and NULL are different thresholds, and the value must reach
    the column as an INT: `_clean` would hand SQLAlchemy the string `'3'`, which
    SQLite stores as text, and the Effective-Low comparison would then be
    comparing a number against a string.
    """

    def test_a_new_product_has_no_threshold(self, catalog_service):
        """Opt-in like the quantity: creating a product commits to nothing."""
        pid = catalog_service.create_product(description='Fresh')
        assert catalog_service.get_product(pid).reorder_threshold is None

    def test_create_may_carry_a_threshold(self, catalog_service):
        pid = catalog_service.create_product(description='Watched',
                                             reorder_threshold='3')
        assert catalog_service.get_product(pid).reorder_threshold == 3

    def test_create_with_a_blank_threshold_stores_null(self, catalog_service):
        """A blank string is what an untouched form field submits, so it has to
        mean the same thing as an omitted argument — not `0`, which is a real
        threshold."""
        pid = catalog_service.create_product(description='Blank field',
                                             reorder_threshold='')
        assert catalog_service.get_product(pid).reorder_threshold is None

    def test_the_value_is_stored_as_an_int_not_as_a_string(
            self, catalog_service):
        """The reason this field needs a branch of its own at all.

        `update_product`'s `else: _clean(value)` tail passes strings through
        unparsed, and SQLite keeps `'3'` in an INTEGER column as TEXT — so the
        predicate's `quantity_on_hand <= reorder_threshold` would compare a
        number against a string and answer wrongly rather than loudly. Asserted
        on the TYPE, because `'3' == 3` is False in Python but the column would
        still read back as something.
        """
        pid = catalog_service.create_product(description='Typed',
                                             reorder_threshold='3')
        stored = catalog_service.get_product(pid).reorder_threshold
        assert stored == 3
        assert isinstance(stored, int)

        assert catalog_service.update_product(pid,
                                              reorder_threshold='5') is True
        stored = catalog_service.get_product(pid).reorder_threshold
        assert stored == 5
        assert isinstance(stored, int)

    def test_zero_is_a_threshold_not_a_clear(self, catalog_service):
        """The distinction a truthiness test would lose: `0` means "tell me the
        moment this runs out", which is the strictest threshold there is, not
        the absence of one."""
        pid = catalog_service.create_product(description='Zero rule')
        assert catalog_service.update_product(pid,
                                              reorder_threshold='0') is True
        product = catalog_service.get_product(pid)
        assert product.reorder_threshold == 0
        assert product.reorder_threshold is not None

    def test_an_integer_argument_is_accepted_too(self, catalog_service):
        """The route hands strings; a caller that already has an int must not
        have to stringify it to be understood."""
        pid = catalog_service.create_product(description='Typed caller')
        assert catalog_service.update_product(pid, reorder_threshold=7) is True
        assert catalog_service.get_product(pid).reorder_threshold == 7

    @pytest.mark.parametrize('cleared', ['', '   ', None],
                             ids=['blank', 'whitespace', 'none'])
    def test_a_cleared_value_stores_null(self, catalog_service, cleared):
        pid = catalog_service.create_product(description='Unwatched',
                                             reorder_threshold='3')
        assert catalog_service.update_product(
            pid, reorder_threshold=cleared) is True
        assert catalog_service.get_product(pid).reorder_threshold is None

    def test_an_absent_key_leaves_the_threshold_alone(self, catalog_service):
        """The partial-update rule, unchanged: an update that never mentions the
        threshold must not remove it."""
        pid = catalog_service.create_product(description='Untouched',
                                             reorder_threshold='3')
        assert catalog_service.update_product(pid,
                                              description='Renamed') is True
        assert catalog_service.get_product(pid).reorder_threshold == 3

    def test_a_zero_padded_string_is_the_magnitude_it_names(
            self, catalog_service):
        """The same rule the quantity gets, from the same shared parse: the form
        bounds the MAGNITUDE, and `int()` refuses a digit string longer than
        4300, so a padded value must not die here."""
        pid = catalog_service.create_product(description='Padded',
                                             reorder_threshold='007')
        assert catalog_service.get_product(pid).reorder_threshold == 7

        assert catalog_service.update_product(
            pid, reorder_threshold='0' * 5000) is True
        assert catalog_service.get_product(pid).reorder_threshold == 0

    @pytest.mark.parametrize('bad', [2.9, Decimal('2.9'), True, -5,
                                     2147483648, '-5', 'abc'],
                             ids=['float', 'decimal', 'bool', 'negative-int',
                                  'over-int32', 'negative-string',
                                  'not-a-number'])
    def test_a_value_the_column_cannot_hold_is_refused_not_truncated(
            self, catalog_service, bad):
        """The service's own type/bounds contract, shared with the quantity.

        `int()` honours neither: `int(2.9)` is 2 and `int(True)` is 1, so an
        accidental float or boolean from a non-form caller would set a silently
        WRONG threshold — and a wrong threshold is a wrong reorder signal on
        every page that reads it afterwards. Refused instead, which
        `update_product` reports as False, leaving the stored value exactly as
        it was.
        """
        pid = catalog_service.create_product(description='Guarded',
                                             reorder_threshold='3')
        before = catalog_service.get_product(pid).reorder_threshold

        assert catalog_service.update_product(pid, reorder_threshold=bad) \
            is False

        assert catalog_service.get_product(pid).reorder_threshold == before == 3

    def test_a_bad_threshold_on_create_writes_no_product(self, catalog_service,
                                                         product_ids):
        """Refused before the insert rather than after it: a create that raises
        must not leave a half-configured product behind for the operator to
        find."""
        assert catalog_service.create_product(description='Guarded',
                                              reorder_threshold=2.9) is None
        assert product_ids() == set()

    def test_the_threshold_is_recorded_in_the_audit_snapshot(
            self, catalog_service, monkeypatch):
        """`to_dict()` is what the audit log stores, so a column missing from it
        is a column whose history cannot be read back. `0` in particular has to
        arrive as `0` rather than as something empty-looking."""
        records = []

        def _capture(operation, status, **kwargs):
            records.append((operation, status, kwargs.get('item_after')))

        monkeypatch.setattr('app.logging_config.log_audit_operation', _capture)

        pid = catalog_service.create_product(description='Audited',
                                             reorder_threshold='0')
        assert records[-1][0] == 'create_product'
        assert records[-1][2]['reorder_threshold'] == 0

        assert catalog_service.update_product(pid,
                                              reorder_threshold='3') is True
        assert records[-1][0] == 'update_product'
        assert records[-1][2]['reorder_threshold'] == 3

    def test_writing_a_threshold_touches_neither_quantity_column(
            self, catalog_service):
        """The threshold is a rule ABOUT the count, not a count. Setting one is
        not an assertion that anybody looked in the bin, so the stamp must not
        move — compared for equality against the value captured first, since a
        `>=` would pass whether or not it moved."""
        pid = catalog_service.create_product(description='Ruled',
                                             quantity_on_hand='4')
        stamp = _stored_stamp(catalog_service, pid)
        assert stamp is not None

        assert catalog_service.update_product(pid,
                                              reorder_threshold='3') is True
        product = catalog_service.get_product(pid)
        assert product.reorder_threshold == 3
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_clearing_the_threshold_leaves_the_quantity_alone(
            self, catalog_service):
        """The other direction, and the one an over-eager "clear the stock
        fields" implementation would get wrong."""
        pid = catalog_service.create_product(description='Ruled then not',
                                             quantity_on_hand='4',
                                             reorder_threshold='3')
        stamp = _stored_stamp(catalog_service, pid)

        assert catalog_service.update_product(pid,
                                              reorder_threshold='') is True
        product = catalog_service.get_product(pid)
        assert product.reorder_threshold is None
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp

    def test_the_shared_parse_still_refuses_in_the_quantitys_own_name(
            self, catalog_service):
        """A tripwire on the Story 5.2 extraction, not a new rule.

        The type/bounds parse now lives in one helper shared by both columns,
        and the field name is a parameter for exactly one reason: so a refusal
        names the field the CALLER passed. If that parameter is ever dropped or
        crossed over, every quantity refusal starts blaming `reorder_threshold`
        — a message that sends the operator to the wrong field — while every
        behavioural test above goes on passing.
        """
        from app.mariadb_catalog_service import _parse_stored_count

        with pytest.raises(TypeError) as type_error:
            _parse_stored_count('quantity_on_hand', 2.9)
        assert str(type_error.value) == (
            'quantity_on_hand must be an int or a digit string, not float')

        with pytest.raises(ValueError) as value_error:
            _parse_stored_count('quantity_on_hand', -5)
        assert str(value_error.value) == (
            'quantity_on_hand must be between 0 and 2147483647, not -5')

        # The third refusal is the one the extraction ADDED (the branch around
        # `int()`), and it is the only one of the three whose wording is not
        # inherited — so it is where a crossed-over field name would be both
        # likeliest and least visible. Pinned here for `quantity_on_hand`
        # because every other test of this branch passes `reorder_threshold`:
        # without this line a swap confined to it would leave the whole suite
        # green while quantity refusals blamed the wrong column.
        with pytest.raises(ValueError) as parse_error:
            _parse_stored_count('quantity_on_hand', 'abc')
        assert str(parse_error.value) == (
            "quantity_on_hand must be an int or a digit string, not 'abc'")

        with pytest.raises(TypeError) as threshold_error:
            _parse_stored_count('reorder_threshold', 2.9)
        assert str(threshold_error.value).startswith('reorder_threshold ')

    @pytest.mark.parametrize('value, expected_in_message', [
        ('abc', "'abc'"),
        # Still 5000 significant digits after the zero strip, so `int()` refuses
        # it outright rather than the bounds check catching an over-large
        # number. Truncated in the message: an audit record is no place for a
        # 5000-character submission.
        ('9' * 5000, "'99999999999999999999999999999999…'"),
    ], ids=['not-a-number', 'past-the-int-conversion-limit'])
    def test_a_string_int_itself_gives_up_on_is_refused_by_field_name(
            self, value, expected_in_message):
        """The two refusals that would otherwise escape as CPython's own text.

        `int()` is not total over strings, and neither way it fails names the
        field or even says an ARGUMENT was wrong — `invalid literal for int()`
        and `Exceeds the limit (4300 digits)` are both about a conversion the
        caller never asked for by name. Since the service's handler logs the
        exception and returns a generic failure, that message is all the record
        has to say which argument to look at.
        """
        from app.mariadb_catalog_service import _parse_stored_count

        with pytest.raises(ValueError) as refusal:
            _parse_stored_count('reorder_threshold', value)
        message = str(refusal.value)
        assert message.startswith(
            'reorder_threshold must be an int or a digit string, not ')
        assert expected_in_message in message
        # Not CPython's own wording, which is what this test exists to displace.
        assert 'invalid literal' not in message
        assert 'Exceeds the limit' not in message

    def test_a_refusal_does_not_quote_the_whole_submission_back(self):
        """The truncation is the point: unbounded input goes into a log line."""
        from app.mariadb_catalog_service import _parse_stored_count

        with pytest.raises(ValueError) as refusal:
            _parse_stored_count('reorder_threshold', 'x' * 5000)
        assert len(str(refusal.value)) < 120

    @pytest.mark.parametrize('value, expected_fragment', [
        # Only 4000 significant digits, so it is UNDER CPython's 4300-digit
        # conversion ceiling: `int()` accepts it happily and the bounds check
        # is what refuses it. That path quoted the value back whole.
        ('9' * 4000, '99999999999999999999999999999999…'),
        # An int argument has no ceiling of its own, and rendering one past
        # 4300 digits raises CPython's `Exceeds the limit` ValueError from
        # inside the f-string building the refusal — so the field-named
        # message was never constructed and CPython's escaped in its place.
        (10 ** 5000, 'an integer past the digit-conversion limit'),
    ], ids=['parses-then-overflows', 'too-large-to-render'])
    def test_the_bounds_refusal_is_bounded_too(self, value, expected_fragment):
        """The sibling of the truncation above, on the other refusal.

        `_parse_stored_count` has two refusals that quote the value back, and
        for a while only one of them was bounded — so the guarded path was the
        one an operator could not reach (the form caps significant digits at
        ten) while the unguarded one took whatever any service caller passed
        and handed it to `log_audit_operation` as `error_details`.
        """
        from app.mariadb_catalog_service import _parse_stored_count

        with pytest.raises(ValueError) as refusal:
            _parse_stored_count('reorder_threshold', value)
        message = str(refusal.value)
        assert message.startswith('reorder_threshold must be between 0 and ')
        assert expected_fragment in message
        assert len(message) < 120
        # Not CPython's own wording: the whole point is that the record says
        # which argument was wrong.
        assert 'Exceeds the limit' not in message

    def test_zero_padding_is_still_the_magnitude_it_names(self):
        """The escape hatch above must not have swallowed the case the strip
        exists for: `'0' * 5000` is the number zero, not an over-long string."""
        from app.mariadb_catalog_service import _parse_stored_count

        assert _parse_stored_count('reorder_threshold', '0' * 5000) == 0


# --- Story 5.3: the manual stock status's write contract --------------------


@pytest.mark.unit
class TestProductStockStatusWriteContract:
    """FR28/FR29/FR31's stored half: one NOT NULL string and its date.

    Shaped like the quantity's contract rather than the threshold's, because
    like the quantity it is TWO columns moving as one — and the interesting
    rule is the same one: the date moves only on a real ASSERTION. What differs,
    and what every re-stamp test below is really about, is that the control is a
    `<select>` with a non-empty default. It posts its key, carrying a VALID
    value, on literally every save, so there is not even the blank-means-
    untouched escape hatch a text input has: only a CHANGED value can mean
    "the operator asserted something".

    Every "unchanged" assertion compares for equality against the exact datetime
    captured first; a `>=` would pass whether or not the stamp moved.
    """

    def _stored_status_stamp(self, catalog_service, product_id):
        return catalog_service.get_product(product_id).stock_status_at

    def test_a_new_product_has_no_assertion(self, catalog_service):
        """The default, and the reason the column is NOT NULL with one:
        `unknown` is a stored value meaning "nobody has said anything", so there
        is no NULL-vs-`unknown` distinction for a reader to get wrong — and no
        date, because no assertion has been made."""
        pid = catalog_service.create_product(description='Fresh')
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None

    def test_a_new_product_is_not_effective_low(self, catalog_service):
        """The default has to be inert. A default of `ok` would be an opinion
        nobody expressed; a default that read as LOW would put the whole catalog
        on the reorder list Story 5.6 builds."""
        pid = catalog_service.create_product(description='Fresh')
        assert catalog_service.get_product(pid).is_effective_low is False

    @pytest.mark.parametrize('status', ['ok', 'low', 'out'])
    def test_create_may_carry_an_assertion_and_is_stamped(self, catalog_service,
                                                          status):
        pid = catalog_service.create_product(description='Asserted at birth',
                                             stock_status=status)
        product = catalog_service.get_product(pid)
        assert product.stock_status == status
        assert product.stock_status_at is not None

    def test_create_with_unknown_stores_unknown_and_no_date(self,
                                                            catalog_service):
        """Explicitly choosing `Not set` on the create form is the same state as
        not choosing anything — including the absence of a date, since choosing
        "no opinion" is not an assertion to date."""
        pid = catalog_service.create_product(description='Explicitly unset',
                                             stock_status='unknown')
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None

    def test_the_first_assertion_stamps(self, catalog_service):
        """`unknown` -> `low`: the flag is set and dated, on a product that
        tracks no quantity and has no threshold. That combination is the whole
        point of FR29 — flagging something low is never gated on counting it."""
        pid = catalog_service.create_product(description='Flag me')
        assert catalog_service.update_product(pid, stock_status='low') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at is not None
        assert product.quantity_on_hand is None
        assert product.reorder_threshold is None
        assert product.is_effective_low is True

    def test_reposting_the_same_status_leaves_the_date(self, catalog_service):
        """THE defect this rule exists to prevent, at the service boundary.

        The edit form renders the status pre-selected, so every browser save
        re-posts it — and unlike the quantity there is no value a browser can
        send that means "untouched". If key presence were the trigger, fixing a
        typo in the description would re-date an assertion made three months
        ago, destroying exactly the staleness signal FR31 asks to be surfaced.
        """
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Flagged',
                                             stock_status='low')
        old = _backdate_status_stamp(catalog_service, pid,
                                     datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(pid, stock_status='low') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == old

    def test_an_unrelated_field_edit_leaves_the_date(self, catalog_service):
        """The same rule from the other direction, and the shape of every real
        browser save: a description change that carries the pre-selected status
        along with it is not a new assertion."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Typo',
                                             stock_status='out')
        old = _backdate_status_stamp(catalog_service, pid,
                                     datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, description='Typo fixed', stock_status='out') is True
        product = catalog_service.get_product(pid)
        assert product.description == 'Typo fixed'
        assert product.stock_status_at == old

    @pytest.mark.parametrize('changed_to', ['out', 'ok'])
    def test_a_changed_status_moves_the_date(self, catalog_service, changed_to):
        """A different status is an assertion on its own terms, in EITHER
        direction: deciding the shelf has refilled is as much an act as
        deciding it has emptied."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Changed',
                                             stock_status='low')
        old = _backdate_status_stamp(catalog_service, pid,
                                     datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, stock_status=changed_to) is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == changed_to
        assert product.stock_status_at > old

    def test_returning_to_unknown_clears_the_date(self, catalog_service):
        """Withdrawing the assertion. The date must go with it: `unknown` is the
        ABSENCE of an opinion, and `Not set (set 3 months ago)` would put a date
        on a field asserting nothing — exactly as an age beside an untracked
        quantity would."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Withdrawn',
                                             stock_status='low')
        _backdate_status_stamp(catalog_service, pid,
                               datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(
            pid, stock_status='unknown') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'unknown'
        assert product.stock_status_at is None
        assert product.is_effective_low is False

    def test_a_missing_date_on_an_asserted_status_is_repaired(self,
                                                              catalog_service):
        """A state this write contract otherwise makes impossible — a flag with
        no record of when it was raised. Re-posting the same status repairs it
        rather than leaving the assertion permanently ageless, which would
        render as a claim with no staleness at all."""
        pid = catalog_service.create_product(description='Ageless',
                                             stock_status='low')
        _backdate_status_stamp(catalog_service, pid, None)
        assert self._stored_status_stamp(catalog_service, pid) is None

        assert catalog_service.update_product(pid, stock_status='low') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at is not None

    def test_an_absent_key_leaves_both_columns_alone(self, catalog_service):
        """The partial-update rule, unchanged: an update that never mentions the
        status must not withdraw the assertion, and must not re-date it
        either — nobody asserted anything."""
        pid = catalog_service.create_product(description='Untouched',
                                             stock_status='low')
        stamp = self._stored_status_stamp(catalog_service, pid)

        assert catalog_service.update_product(pid, description='Renamed') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == stamp

    @pytest.mark.parametrize('bad', ['', '   ', 'LOW', 'Low', 'bogus',
                                     ' low ', 'x' * 5000],
                             ids=['blank', 'whitespace', 'upper', 'title',
                                  'not-a-member', 'padded', 'oversized'])
    def test_a_value_outside_the_four_is_refused_and_writes_nothing(
            self, catalog_service, bad):
        """The service's own contract, and the reason a blank is a REFUSAL here
        where `_parse_stored_count` maps one to a clear.

        That function's columns are nullable and None is a real stored state.
        This column cannot be NULL, so a blank has no destination — and mapping
        it silently onto `unknown` would let a truncated or malformed POST
        quietly erase a `low` flag, which is the one outcome this field must
        never produce by accident. Case and padding are refused for the same
        reason: the four values are a closed machine vocabulary, so `' low '` is
        a caller bug, not a typing slip to be forgiven.
        """
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Guarded',
                                             stock_status='low')
        old = _backdate_status_stamp(catalog_service, pid,
                                     datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(pid, stock_status=bad) is False

        product = catalog_service.get_product(pid)
        assert product.stock_status == 'low'
        assert product.stock_status_at == old

    @pytest.mark.parametrize('bad', [7, 0, None, True, ['low'],
                                     StockStatus.LOW],
                             ids=['int', 'zero', 'none', 'bool', 'list',
                                  'enum-member'])
    def test_a_non_string_is_refused_and_writes_nothing(self, catalog_service,
                                                        bad):
        """The column stores the STRING, so the enum MEMBER is refused too — it
        is the likeliest of these to be passed by accident and the one whose
        `str()` (`StockStatus.LOW`) would store something the predicate could
        never match. `None` is refused rather than treated as "not provided":
        not providing the field is spelled by omitting the argument, and giving
        `None` a meaning here would be giving this field the "clear" state it
        deliberately does not have."""
        pid = catalog_service.create_product(description='Guarded',
                                             stock_status='low')

        assert catalog_service.update_product(pid, stock_status=bad) is False
        assert catalog_service.get_product(pid).stock_status == 'low'

    def test_a_bad_status_on_create_writes_no_product(self, catalog_service,
                                                      product_ids):
        """Refused before the insert rather than after it: a create that raises
        must not leave a half-configured product behind for the operator to
        find."""
        assert catalog_service.create_product(description='Guarded',
                                              stock_status='bogus') is None
        assert product_ids() == set()

    def test_a_refusal_names_the_field_and_bounds_the_value(self):
        """The refusal is what the caller's handler writes into the audit
        record as `error_details`, so it is operator-supplied text going into a
        log line: it must name the field (nothing else in the record says WHICH
        argument was wrong) and must not quote the whole submission back."""
        from app.mariadb_catalog_service import _apply_stock_status_assertion
        from app.database import Product

        product = Product(internal_id='PR0DSTAT01')

        with pytest.raises(ValueError) as refusal:
            _apply_stock_status_assertion(product, 'x' * 5000)
        message = str(refusal.value)
        assert message.startswith('stock_status must be one of ')
        assert len(message) < 160

        with pytest.raises(TypeError) as type_error:
            _apply_stock_status_assertion(product, 7)
        assert str(type_error.value).startswith('stock_status must be one of ')
        assert 'int' in str(type_error.value)

    def test_stock_status_at_is_not_accepted_from_a_caller(self,
                                                           catalog_service):
        """It is DERIVED from the act of asserting a status, never supplied.

        A caller able to set it could claim an assertion was made at a time
        nobody made one — precisely the lie the age display exists to prevent —
        so the name is absent from `_PRODUCT_FIELDS` and is dropped in silence,
        exactly as `quantity_verified_at` and `internal_id` are.
        """
        from datetime import datetime

        from app.mariadb_catalog_service import _PRODUCT_FIELDS

        assert 'stock_status_at' not in _PRODUCT_FIELDS

        pid = catalog_service.create_product(description='No backdating',
                                             stock_status='low')
        stamp = self._stored_status_stamp(catalog_service, pid)
        assert catalog_service.update_product(
            pid, stock_status_at=datetime(1999, 1, 1)) is True
        assert self._stored_status_stamp(catalog_service, pid) == stamp

    def test_the_status_pair_is_recorded_in_the_audit_snapshot(
            self, catalog_service, monkeypatch):
        """`to_dict()` is what the audit log stores, so a column missing from it
        is a column whose history cannot be read back — and this pair IS the
        assertion, so without it no record answers "who said this was low, and
        when"."""
        records = []

        def _capture(operation, status, **kwargs):
            records.append((operation, status, kwargs.get('item_after')))

        monkeypatch.setattr('app.logging_config.log_audit_operation', _capture)

        pid = catalog_service.create_product(description='Audited')
        assert records[-1][0] == 'create_product'
        # Even the default is in the snapshot: `unknown` is a stored value.
        assert records[-1][2]['stock_status'] == 'unknown'
        assert records[-1][2]['stock_status_at'] is None

        assert catalog_service.update_product(pid, stock_status='low') is True
        assert records[-1][0] == 'update_product'
        assert records[-1][2]['stock_status'] == 'low'
        # ISO string, like every other timestamp in the snapshot.
        assert isinstance(records[-1][2]['stock_status_at'], str)

    def test_asserting_a_status_touches_no_count_column(self, catalog_service):
        """FR29: the status is an assertion about the SHELF, not a count. It is
        not evidence that anybody counted anything, so neither quantity column
        nor the threshold may move — compared for equality against the values
        captured first, since a `>=` would pass whether or not the stamp
        moved."""
        pid = catalog_service.create_product(description='Counted and flagged',
                                             quantity_on_hand='4',
                                             reorder_threshold='3')
        stamp = _stored_stamp(catalog_service, pid)
        assert stamp is not None

        assert catalog_service.update_product(pid, stock_status='out') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'out'
        assert product.quantity_on_hand == 4
        assert product.quantity_verified_at == stamp
        assert product.reorder_threshold == 3

    def test_a_count_write_touches_no_status_column(self, catalog_service):
        """The other direction, and the one an over-eager "sync the stock
        fields" implementation would get wrong: counting four onto a shelf you
        flagged `out` does not withdraw the flag. Only the operator does
        (Story 5.5 gives a RECEIPT that power, and only for a manual low)."""
        from datetime import datetime, timedelta

        pid = catalog_service.create_product(description='Flagged then counted',
                                             stock_status='out')
        old = _backdate_status_stamp(catalog_service, pid,
                                     datetime.now() - timedelta(days=95))

        assert catalog_service.update_product(pid, quantity_on_hand='4',
                                              reorder_threshold='3') is True
        product = catalog_service.get_product(pid)
        assert product.stock_status == 'out'
        assert product.stock_status_at == old

    def test_a_manual_flag_and_the_threshold_branch_are_independent(
            self, catalog_service):
        """FR30's OR, read back through the service the way the detail page
        does. `ok` does not suppress a crossed threshold — the operator's
        opinion cannot outrank a count they recorded against a threshold they
        set — and `low` does not need one."""
        flagged = catalog_service.create_product(description='Flag only',
                                                 stock_status='low')
        crossed = catalog_service.create_product(description='Threshold only',
                                                 quantity_on_hand='2',
                                                 reorder_threshold='3',
                                                 stock_status='ok')
        quiet = catalog_service.create_product(description='Neither',
                                               quantity_on_hand='9',
                                               reorder_threshold='3',
                                               stock_status='ok')

        assert catalog_service.get_product(flagged).is_effective_low is True
        assert catalog_service.get_product(crossed).is_effective_low is True
        assert catalog_service.get_product(quiet).is_effective_low is False


@pytest.mark.unit
class TestProductLocationWrite:
    """FR27's stored half — plain optional strings, cleaned like every other."""

    def test_create_and_update_store_the_pair(self, catalog_service):
        pid = catalog_service.create_product(description='Shelved',
                                             location='  Bin 7  ',
                                             sub_location='Left tray')
        product = catalog_service.get_product(pid)
        assert product.location == 'Bin 7'  # `_clean` trims, as elsewhere
        assert product.sub_location == 'Left tray'

        assert catalog_service.update_product(pid, location='Rack 3') is True
        assert catalog_service.get_product(pid).location == 'Rack 3'

    def test_blank_clears_to_null(self, catalog_service):
        """Backfill-forward: an emptied optional field stores NULL, not ''. It
        matters more here than usual — a '' row would be filtered out of the
        suggestion query anyway, so a stored blank would be invisible AND
        undeletable-looking."""
        pid = catalog_service.create_product(description='Unshelved',
                                             location='Bin 7',
                                             sub_location='Left tray')
        assert catalog_service.update_product(pid, location='',
                                              sub_location='   ') is True
        product = catalog_service.get_product(pid)
        assert product.location is None
        assert product.sub_location is None

    def test_an_absent_key_leaves_the_pair_alone(self, catalog_service):
        pid = catalog_service.create_product(description='Still shelved',
                                             location='Bin 7')
        assert catalog_service.update_product(pid, description='Renamed') is True
        assert catalog_service.get_product(pid).location == 'Bin 7'


@pytest.mark.unit
class TestProductLocationSuggestions:
    """`get_product_location_suggestions` — the catalog half of FR27's shared
    vocabulary, held to the same ordering and guard contract as the item half so
    the merge of the two is equivalent to one query over both tables."""

    @pytest.fixture
    def stocked(self, catalog_service):
        for description, location, sub_location in (
            ('a', 'Bin 7', 'Left tray'),
            ('b', 'Bin 70', 'Right tray'),
            ('c', 'Attic', 'Left tray'),
            ('d', 'Top Bin', 'Under'),
            ('e', 'bin 7', 'Left tray'),      # a case variant of Bin 7
            ('f', None, None),                # untouched by this story
        ):
            catalog_service.create_product(description=description,
                                           location=location,
                                           sub_location=sub_location)
        return catalog_service

    def test_unknown_field_raises_value_error(self, catalog_service):
        """Which is what the route turns into its existing 400 — the same
        contract both `get_field_value_suggestions` methods carry."""
        with pytest.raises(ValueError):
            catalog_service.get_product_location_suggestions('vendor')

    def test_unfiltered_is_alphabetical_and_deduped(self, stocked):
        """No query means one tier: alphabetized case-insensitively, with the
        case variants of one value collapsed to a single offered spelling."""
        assert stocked.get_product_location_suggestions('location') == [
            'Attic', 'Bin 7', 'Bin 70', 'Top Bin']

    def test_the_ranking_tiers(self, stocked):
        """Exact match, then starts-with, then contains — the endpoint's rule,
        mirrored here so the merged answer cannot be ordered differently from
        an unmerged one."""
        assert stocked.get_product_location_suggestions(
            'location', query='bin') == ['Bin 7', 'Bin 70', 'Top Bin']
        assert stocked.get_product_location_suggestions(
            'location', query='bin 7') == ['Bin 7', 'Bin 70']

    def test_limit_is_respected(self, stocked):
        assert stocked.get_product_location_suggestions(
            'location', limit=2) == ['Attic', 'Bin 7']

    def test_sub_location_is_scoped_by_its_parent(self, stocked):
        """The one behavioural difference from the item half: the parent
        compared is `Product.location`, so this answers "what sub-locations do
        PRODUCTS stored at Bin 7 use"."""
        assert stocked.get_product_location_suggestions(
            'sub_location', location='Bin 7') == ['Left tray']
        assert stocked.get_product_location_suggestions(
            'sub_location', location='Bin 70') == ['Right tray']
        assert stocked.get_product_location_suggestions('sub_location') == [
            'Left tray', 'Right tray', 'Under']

    def test_unstorable_and_overlong_queries_answer_nothing_unqueried(
            self, stocked):
        """The same pair of guards the item half carries, and for the same
        reason: this method runs on the SAME request, so a guard missing here
        would put products into a merged answer the item half correctly refused
        to contribute to. Asserted with an emitted-SQL spy, because a guard that
        ran after the query would still be a query."""
        from sqlalchemy import event
        from app.utils.sql_text import SEARCH_QUERY_MAX_LENGTH

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(stocked.engine, 'before_cursor_execute', record)
        try:
            assert stocked.get_product_location_suggestions(
                'location', query='\x00') == []
            assert stocked.get_product_location_suggestions(
                'location', query='a\x00b') == []
            assert stocked.get_product_location_suggestions(
                'location', query='a' * (SEARCH_QUERY_MAX_LENGTH + 1)) == []
            assert stocked.get_product_location_suggestions(
                'sub_location', location='a\x00b') == []
        finally:
            event.remove(stocked.engine, 'before_cursor_execute', record)

        assert statements == [], statements

    def test_the_location_fields_are_not_in_the_dispatch_whitelist(self):
        """The membership that would break the endpoint rather than extend it.

        `FIELD_SUGGESTION_COLUMNS` decides which service answers a field
        INSTEAD of the other; `location` there would point the item form's own
        lookup at the products table. The bidirectional vocabulary is built by
        calling this method IN ADDITION, which is why its columns live in a
        private map of their own.
        """
        from app.mariadb_catalog_service import (FIELD_SUGGESTION_COLUMNS,
                                                 _PRODUCT_LOCATION_COLUMNS)
        assert set(_PRODUCT_LOCATION_COLUMNS) == {'location', 'sub_location'}
        assert not (set(_PRODUCT_LOCATION_COLUMNS)
                    & set(FIELD_SUGGESTION_COLUMNS))
