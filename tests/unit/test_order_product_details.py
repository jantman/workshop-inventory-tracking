"""Filling in a product an order created, without a second purchase (feature 044).

Issue #156. An Amazon order capture creates products that carry only what the
order page stated: a description, the ASIN and the purchase. The order review
told the operator to capture each item's listing afterwards, promising that this
would attach to the same product without writing a second purchase. It could
not. Every path through the single-listing capture ended in ``record_purchase``,
and the two questions it raised -- "you may have captured this already" and
"this item number already names something" -- had no answer that avoided one.

This suite covers the details-only capture that closes that gap, the one
question that replaces the two when the listing belongs to an order already
captured, the order page's checklist of products still missing details, and the
order capture that reads each line's listing itself.
"""

import json
import re
from datetime import datetime
from unittest.mock import patch

import pytest

from app.catalog_service import (
    AMAZON_ORDER_VENDOR,
    AMAZON_VENDOR,
    CatalogService,
)
from app.exceptions import ItemNotFoundError, ValidationError
from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    AmazonOrder,
    AmazonOrderLine,
    ImageCaptureResult,
    ListingCapture,
    ListingMatch,
    OrderCaptureResult,
)
from app.utils.clock import local_now

pytestmark = pytest.mark.unit


ASIN = 'B0CXYZ1234'
ORDER_NUMBER = '112-4455667-8899001'
ORDER_DATE_TEXT = 'September 14, 2026'
LISTING_URL = f'https://www.amazon.com/dp/{ASIN}'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def listing_payload(**overrides):
    """What the capture agent reads off a listing page, as the hidden field."""
    data = {
        'version': 1,
        'source_url': LISTING_URL,
        'vendor_item_id': ASIN,
        'listing_title': 'M3 Socket Head Cap Screws, 100 pack',
        'brand': 'Acme Fasteners',
        'price': '8.99',
        'description_text': 'Alloy steel, black oxide finish.',
        'specifications': [
            {'name': 'Thread Size', 'value': 'M3'},
            {'name': 'Length', 'value': '10 mm'},
        ],
    }
    data.update(overrides)
    return data


def todays_date_text():
    """Today as Amazon's order page writes a date.

    The confirmation page asks about an order purchase with *today's* date,
    because the bookmarklet sends none -- so a test that needs the page to
    recognize the order dates the order today rather than trusting the clock to
    sit within ninety days of a fixed date.
    """
    now = local_now()
    return f"{now:%B} {now.day}, {now:%Y}"


def build_order(lines=None, order_date=ORDER_DATE_TEXT):
    """An Amazon order as the capture agent reads one off the order page."""
    return AmazonOrder.from_payload({
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': ORDER_NUMBER,
        'order_date': order_date,
        'source_url': (
            'https://www.amazon.com/your-orders/order-details'
            f'?orderID={ORDER_NUMBER}'
        ),
        'lines': lines if lines is not None else [
            {'asin': ASIN, 'title': 'M3 Socket Head Cap Screws',
             'quantity': 1, 'unit_price': '8.99'},
        ],
    })


def capture_the_order(catalog, order=None):
    """Capture an order the way its review's defaults would, and return its line."""
    order = order or build_order()
    catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
        line.form_key: {'include': True} for line in order.lines
    })
    return catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]


class TestTheReportedFailure:
    """SC-001: issue #156 in one test, written before the fix and seen failing."""

    def test_a_listing_capture_after_its_order_fills_the_product_in(
        self, catalog, client
    ):
        recorded = capture_the_order(catalog)
        product = catalog.get_product(recorded.product_id)
        assert product.specifications == []

        response = client.post('/products/capture', data={
            'url': LISTING_URL,
            'vendor': AMAZON_VENDOR,
            'vendor_item_id': ASIN,
            'listing_title': 'M3 Socket Head Cap Screws, 100 pack',
            'listing': json.dumps(listing_payload()),
            'intent': 'details',
            'details_product_id': str(recorded.product_id),
            'return_order': ORDER_NUMBER,
        })

        assert response.status_code == 302
        assert f'/products/orders/{AMAZON_VENDOR}/{ORDER_NUMBER}' in response.location

        product = catalog.get_product(recorded.product_id)
        names = {row.name for row in product.specifications}
        assert {'Thread Size', 'Length', 'Description'} <= names
        assert len(catalog.get_purchase_history(recorded.product_id)) == 1


# A real UPC-A with a valid check digit, so 016's promotion accepts it.
VALID_UPC = '036000291452'


def listing(**overrides):
    return ListingCapture.from_data(listing_payload(**overrides))


def thin_product(catalog, **fields):
    """A product holding only what an order page states, plus its ASIN."""
    fields.setdefault('description', 'M3 Socket Head Cap Screws')
    return catalog.create_product(
        identifiers=[{'id_type': 'VENDOR', 'value': ASIN, 'vendor': AMAZON_VENDOR}],
        **fields,
    )


def spec_rows(catalog, product_id):
    return {
        row.name: row.value
        for row in catalog.get_product(product_id).specifications
    }


class TestTheListingPayload:
    """The parsed form a line's listing arrives in, and what it contributes."""

    def test_from_data_and_from_json_agree(self):
        raw = json.dumps(listing_payload())
        assert ListingCapture.from_json(raw) == ListingCapture.from_data(json.loads(raw))

    def test_from_data_refuses_what_from_json_refuses(self):
        assert ListingCapture.from_data(None) is None
        assert ListingCapture.from_data([]) is None
        assert ListingCapture.from_data(listing_payload(version=99)) is None
        assert ListingCapture.from_data(listing_payload(source_url='')) is None

    def test_the_description_is_a_row(self):
        names = [entry['name'] for entry in listing().specification_entries()]
        assert names == ['Thread Size', 'Length', 'Description']

    def test_a_barcode_row_is_noticed(self):
        assert listing().has_barcode is False
        with_upc = listing(specifications=[{'name': 'UPC', 'value': VALID_UPC}])
        assert with_upc.has_barcode is True


class TestSpecDifferences:
    """What the confirmation page previews, by the rule the write obeys."""

    def match(self, *rows):
        return ListingMatch(product_id=1, description='x', specifications=tuple(rows))

    def test_absent_names_are_added_and_differing_ones_listed(self):
        added, differing = self.match(
            ('thread size', 'M3'), ('Length', '12 mm'),
        ).spec_differences(listing())

        assert [row['name'] for row in added] == ['Description']
        assert differing == (('Length', '12 mm', '10 mm'),)

    def test_nothing_without_a_listing(self):
        assert self.match().spec_differences(None) == ((), ())


class TestProductsMissingDetails:
    """FR-014 and FR-015: derived from specification rows, nothing stored."""

    def test_an_order_created_product_is_missing(self, catalog):
        recorded = capture_the_order(catalog)
        assert catalog.products_missing_details([recorded.product_id]) == {
            recorded.product_id
        }

    def test_a_product_with_rows_is_not(self, catalog):
        product = catalog.create_product(
            description='Filled in', specifications=[{'name': 'Color', 'value': 'red'}],
        )
        assert catalog.products_missing_details([product.id]) == set()

    def test_no_ids_is_no_query_and_no_answer(self, catalog):
        assert catalog.products_missing_details([]) == set()
        assert catalog.products_missing_details([None]) == set()


class TestFindListingMatch:
    """The read-only lookup the confirmation page is built from."""

    def test_nothing_names_the_item(self, catalog):
        assert catalog.find_listing_match(AMAZON_VENDOR, ASIN) is None
        assert catalog.find_listing_match(AMAZON_VENDOR, '') is None

    def test_a_product_with_no_order_purchase(self, catalog):
        product = thin_product(catalog, manufacturer='Acme')

        match = catalog.find_listing_match(AMAZON_VENDOR, ASIN, LISTING_URL)

        assert match.product_id == product.id
        assert match.manufacturer == 'Acme'
        assert match.from_order is False

    def test_a_product_an_order_created_names_the_order(self, catalog):
        recorded = capture_the_order(catalog)

        match = catalog.find_listing_match(
            AMAZON_VENDOR, ASIN, LISTING_URL, order_date='2026-09-16',
        )

        assert match.product_id == recorded.product_id
        assert match.from_order is True
        assert match.order_purchase_id == recorded.id
        assert match.order_reference == ORDER_NUMBER
        assert match.order_vendor == AMAZON_VENDOR

    def test_an_order_purchase_on_another_product_is_not_this_ones(self, catalog):
        thin_product(catalog)
        elsewhere = catalog.create_product(description='Something else')
        catalog.record_purchase(
            elsewhere.id, vendor=AMAZON_VENDOR, vendor_item_id=ASIN,
            order_date=datetime(2026, 9, 14),
            supplier_order_reference=ORDER_NUMBER,
        )

        match = catalog.find_listing_match(
            AMAZON_VENDOR, ASIN, order_date='2026-09-16',
        )

        assert match.from_order is False

    def test_an_order_outside_the_window_is_not_offered(self, catalog):
        capture_the_order(catalog)

        match = catalog.find_listing_match(
            AMAZON_VENDOR, ASIN, order_date='2027-03-01',
        )

        assert match.from_order is False

    def test_an_unreadable_date_still_finds_the_product(self, catalog):
        product = thin_product(catalog)
        match = catalog.find_listing_match(AMAZON_VENDOR, ASIN, order_date='not a date')
        assert match.product_id == product.id


class TestApplyListingDetails:
    """FR-002 to FR-006: fill blanks, replace only what is named, no purchase."""

    def test_blanks_are_filled_and_no_purchase_is_written(self, catalog):
        product = thin_product(catalog, quantity=5)

        result = catalog.apply_listing_details(
            product.id, listing(),
            proposed={'manufacturer': 'Acme Fasteners',
                      'manufacturer_part_number': 'SHCS-M3-10'},
        )

        after = catalog.get_product(product.id)
        assert after.manufacturer == 'Acme Fasteners'
        assert after.manufacturer_part_number == 'SHCS-M3-10'
        assert spec_rows(catalog, product.id) == {
            'Thread Size': 'M3', 'Length': '10 mm',
            'Description': 'Alloy steel, black oxide finish.',
        }
        assert after.quantity == 5
        assert catalog.get_purchase_history(product.id) == []
        assert set(result.fields_filled) == {'manufacturer', 'manufacturer_part_number'}
        assert result.specifications_added == 3
        assert result.changed_anything is True

    def test_a_held_value_is_kept_unless_named(self, catalog):
        product = thin_product(
            catalog, manufacturer='Old Brand',
            specifications=[{'name': 'Length', 'value': '12 mm'}],
        )

        result = catalog.apply_listing_details(
            product.id, listing(), proposed={'manufacturer': 'Acme Fasteners'},
        )

        assert catalog.get_product(product.id).manufacturer == 'Old Brand'
        assert spec_rows(catalog, product.id)['Length'] == '12 mm'
        assert result.fields_replaced == ()
        assert result.specifications_replaced == 0

    def test_only_the_named_values_are_replaced(self, catalog):
        product = thin_product(
            catalog, manufacturer='Old Brand', location='Shelf A',
            specifications=[{'name': 'Length', 'value': '12 mm'},
                            {'name': 'Thread Size', 'value': 'M4'}],
        )

        result = catalog.apply_listing_details(
            product.id, listing(),
            proposed={'manufacturer': 'Acme Fasteners', 'location': 'Shelf B'},
            replace={'manufacturer', 'spec:length'},
        )

        after = catalog.get_product(product.id)
        assert after.manufacturer == 'Acme Fasteners'
        assert after.location == 'Shelf A'
        rows = spec_rows(catalog, product.id)
        assert rows['Length'] == '10 mm'
        assert rows['Thread Size'] == 'M4'
        assert result.fields_replaced == ('manufacturer',)
        assert result.specifications_replaced == 1

    def test_a_replaced_row_keeps_its_place(self, catalog):
        product = thin_product(
            catalog, specifications=[{'name': 'Length', 'value': '12 mm'},
                                     {'name': 'Color', 'value': 'black'}],
        )

        catalog.apply_listing_details(product.id, listing(), replace={'spec:Length'})

        names = [row.name for row in catalog.get_product(product.id).specifications]
        assert names[:2] == ['Length', 'Color']

    def test_repeating_it_changes_nothing(self, catalog):
        product = thin_product(catalog)
        payload = listing(specifications=[
            {'name': 'Thread Size', 'value': 'M3'},
            {'name': 'UPC', 'value': VALID_UPC},
        ])
        catalog.apply_listing_details(product.id, payload)
        before_rows = spec_rows(catalog, product.id)
        before_ids = sorted(
            (i.id_type, i.value) for i in catalog.get_product(product.id).identifiers
        )

        again = catalog.apply_listing_details(product.id, payload)

        assert again.changed_anything is False
        assert spec_rows(catalog, product.id) == before_rows
        assert sorted(
            (i.id_type, i.value) for i in catalog.get_product(product.id).identifiers
        ) == before_ids
        # And the barcode was promoted the first time, exactly once.
        assert [t for t, _ in before_ids].count('GTIN') == 1

    def test_a_blank_proposal_clears_nothing(self, catalog):
        product = thin_product(catalog, manufacturer='Acme')
        catalog.apply_listing_details(product.id, None, proposed={'manufacturer': '  '})
        assert catalog.get_product(product.id).manufacturer == 'Acme'

    def test_a_refused_value_writes_nothing(self, catalog):
        product = thin_product(catalog)

        with pytest.raises(ValidationError):
            catalog.apply_listing_details(
                product.id, listing(),
                proposed={'manufacturer': 'Acme', 'description': 'x' * 256},
                replace={'description'},
            )

        after = catalog.get_product(product.id)
        assert after.manufacturer is None
        assert after.specifications == []

    def test_a_missing_product_is_not_found(self, catalog):
        with pytest.raises(ItemNotFoundError):
            catalog.apply_listing_details(999999, listing())


def input_tag(html, element_id):
    """The whole <input> tag carrying this id, or None."""
    found = re.search(rf'<input[^>]*\bid="{re.escape(element_id)}"[^>]*>', html)
    return found.group(0) if found else None


def is_checked(html, element_id):
    tag = input_tag(html, element_id)
    assert tag is not None, f"no #{element_id} on the page"
    return re.search(r'\bchecked\b', tag) is not None


def land(client, payload=None):
    """What the bookmarklet's new tab shows: /api/capture with a form body."""
    response = client.post('/api/capture', data={
        'url': LISTING_URL,
        'listing_title': 'M3 Socket Head Cap Screws, 100 pack',
        'listing': json.dumps(payload or listing_payload()),
    })
    assert response.status_code == 200
    return response.get_data(as_text=True)


def confirm(client, **form):
    """Submit the confirmation form, as its fields would carry it."""
    data = {
        'url': LISTING_URL,
        'vendor': AMAZON_VENDOR,
        'vendor_item_id': ASIN,
        'listing_title': 'M3 Socket Head Cap Screws, 100 pack',
        'listing': json.dumps(listing_payload()),
    }
    data.update(form)
    return client.post('/products/capture', data=data)


class TestDetailsOnlyOnTheConfirmationPage:
    """US1: a listing whose product exists can fill it in without a purchase."""

    def test_the_landing_offers_the_choice_and_defaults_to_a_purchase(
        self, catalog, client
    ):
        """FR-001, FR-012"""
        thin_product(catalog)

        html = land(client)

        assert 'id="listing-match"' in html
        assert is_checked(html, 'intent-purchase')
        assert not is_checked(html, 'intent-details')
        assert 'id="order-item-match"' not in html

    def test_a_listing_nothing_names_offers_no_choice(self, client):
        """US1 scenario 7"""
        html = land(client)

        assert 'id="listing-match"' not in html
        assert 'id="intent-details"' not in html

    def test_details_only_records_no_purchase_and_lands_on_the_product(
        self, catalog, client
    ):
        """FR-002, FR-003, FR-020"""
        product = thin_product(catalog, quantity=4)
        payload = listing_payload(images=['https://m.media-amazon.com/images/I/a.jpg'])

        with patch(
            'app.product.routes.store_listing_images',
            return_value=ImageCaptureResult(stored=1),
        ) as stored:
            response = confirm(
                client, intent='details', details_product_id=str(product.id),
                listing=json.dumps(payload),
                manufacturer='Acme Fasteners',
            )

        assert response.status_code == 302
        assert response.location.endswith(f'/products/{product.id}')
        assert catalog.get_purchase_history(product.id) == []
        after = catalog.get_product(product.id)
        assert after.manufacturer == 'Acme Fasteners'
        assert after.quantity == 4
        assert 'Thread Size' in spec_rows(catalog, product.id)
        assert stored.call_args.args[0] == product.id

    def test_only_the_ticked_value_is_replaced(self, catalog, client):
        """FR-004, FR-005"""
        product = thin_product(
            catalog, manufacturer='Old Brand', manufacturer_part_number='OLD-1',
        )

        confirm(
            client, intent='details', details_product_id=str(product.id),
            manufacturer='Acme Fasteners', manufacturer_part_number='NEW-2',
            replace=['manufacturer'],
        )

        after = catalog.get_product(product.id)
        assert after.manufacturer == 'Acme Fasteners'
        assert after.manufacturer_part_number == 'OLD-1'

    def test_held_values_are_shown_beside_their_fields_unticked(self, catalog, client):
        """FR-004: current against proposed, keep by default."""
        thin_product(
            catalog, manufacturer='Old Brand',
            specifications=[{'name': 'Length', 'value': '12 mm'}],
        )

        html = land(client)

        assert 'id="current-manufacturer"' in html
        assert 'Old Brand' in html
        assert not is_checked(html, 'replace-manufacturer')
        assert 'id="spec-differences"' in html
        assert not is_checked(html, 'replace-spec-1')
        assert 'id="spec-added-count"' in html

    def test_the_page_says_when_the_listing_adds_nothing(self, catalog, client):
        """FR-007"""
        thin_product(
            catalog, manufacturer='Acme Fasteners',
            specifications=listing().specification_entries(),
        )

        html = land(client)

        assert 'id="nothing-new"' in html
        assert 'id="spec-differences"' not in html

    def test_without_intent_it_is_the_purchase_it_always_was(self, catalog, client):
        """FR-008: an absent `intent` is today's request."""
        product = thin_product(catalog)

        response = confirm(client, attach_to=str(product.id), quantity='1')

        assert response.status_code == 302
        assert '/receive' in response.location
        assert len(catalog.get_purchase_history(product.id)) == 1

    def test_a_product_that_has_gone_is_a_message_not_a_write(self, catalog, client):
        response = confirm(client, intent='details', details_product_id='999999')

        assert response.status_code == 200
        assert catalog.list_products() == []


class TestOneQuestionAfterAnOrder:
    """US2: the listing of an item an order captured asks one thing, not two."""

    def test_the_landing_names_the_order_and_selects_details_only(
        self, catalog, client
    ):
        """FR-009, FR-010, FR-011"""
        capture_the_order(catalog, build_order(order_date=todays_date_text()))

        html = land(client)

        assert 'id="order-item-match"' in html
        assert ORDER_NUMBER in html
        assert is_checked(html, 'intent-details')
        assert not is_checked(html, 'intent-purchase')
        assert 'id="separate-purchase-consequence"' in html
        assert 'id="duplicate-warning"' not in html
        assert 'id="identifier-warning"' not in html

    def test_a_separate_purchase_asks_nothing_further(self, catalog, client):
        """FR-011: the hidden answers are exactly what capture_order needs."""
        recorded = capture_the_order(
            catalog, build_order(order_date=todays_date_text())
        )

        response = confirm(
            client, intent='purchase',
            details_product_id=str(recorded.product_id),
            acknowledged_duplicate_of=str(recorded.id),
            attach_to=str(recorded.product_id),
            return_order=ORDER_NUMBER,
            quantity='1',
        )

        assert response.status_code == 302
        assert '/receive' in response.location
        assert len(catalog.get_purchase_history(recorded.product_id)) == 2

    def test_the_paste_form_asks_the_one_question_too(self, catalog, client):
        """FR-009 on a re-render: capture_order raised both, one is shown."""
        capture_the_order(catalog, build_order(order_date=todays_date_text()))

        response = client.post('/products/capture', data={'url': LISTING_URL})

        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="order-item-match"' in html
        assert 'id="duplicate-warning"' not in html
        assert 'id="identifier-warning"' not in html

    def test_filing_it_as_a_different_product_says_what_that_costs(
        self, catalog, client
    ):
        """FR-013"""
        thin_product(catalog, manufacturer='Other Co', manufacturer_part_number='X-1')

        response = confirm(
            client, manufacturer='Acme Fasteners', manufacturer_part_number='Y-2',
        )

        html = response.get_data(as_text=True)
        assert 'id="identifier-warning"' in html
        assert 'id="attach-new-consequence"' in html


SECOND_ASIN = 'B0CXYZ5678'


class TestTheOrderChecklist:
    """US3: the order page and the product page say what still needs details."""

    def two_line_order(self, catalog):
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'M3 Socket Head Cap Screws',
             'quantity': 1, 'unit_price': '8.99'},
            {'asin': SECOND_ASIN, 'title': 'PLA Filament 1kg',
             'quantity': 2, 'unit_price': '19.99'},
        ])
        capture_the_order(catalog, order)
        return {
            line.vendor_item_id: line.product_id
            for line in catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)
        }

    def order_page(self, client):
        response = client.get(f'/products/orders/{AMAZON_VENDOR}/{ORDER_NUMBER}')
        assert response.status_code == 200
        return response.get_data(as_text=True)

    def test_every_new_product_reads_as_missing_with_its_listing(self, catalog, client):
        """FR-016, FR-017"""
        self.two_line_order(catalog)

        html = self.order_page(client)

        assert 'id="details-progress"' in html
        assert '2 of 2 product(s) still need details' in html
        assert html.count('details-missing') == 2
        assert f'href="https://www.amazon.com/dp/{ASIN}"' in html
        assert f'href="https://www.amazon.com/dp/{SECOND_ASIN}"' in html

    def test_filling_one_in_moves_the_count(self, catalog, client):
        products = self.two_line_order(catalog)
        catalog.apply_listing_details(products[ASIN], listing())

        html = self.order_page(client)

        assert '1 of 2 product(s) still need details' in html
        assert 'details-captured' in html
        assert f'href="https://www.amazon.com/dp/{ASIN}"' not in html

    def test_an_order_with_nothing_missing_says_it_is_complete(self, catalog, client):
        products = self.two_line_order(catalog)
        for product_id in products.values():
            catalog.apply_listing_details(product_id, listing())

        html = self.order_page(client)

        assert 'Every product on this order has its details' in html
        assert 'details-missing' not in html

    def test_another_vendors_order_page_is_unchanged(self, catalog, client):
        product = catalog.create_product(description='Hex standoff')
        catalog.record_purchase(
            product.id, vendor='McMaster-Carr', vendor_item_id='93505A117',
            supplier_order_reference='PO-7',
        )

        html = client.get('/products/orders/McMaster-Carr/PO-7').get_data(as_text=True)

        assert 'id="details-progress"' not in html
        assert 'details-missing' not in html

    def test_the_product_page_says_it_is_missing_details(self, catalog, client):
        """FR-018"""
        product = thin_product(catalog)

        html = client.get(f'/products/{product.id}').get_data(as_text=True)

        assert 'id="details-missing-notice"' in html
        assert f'href="https://www.amazon.com/dp/{ASIN}"' in html

    def test_a_product_with_details_or_no_listing_is_not_nagged(self, catalog, client):
        filled = thin_product(catalog, specifications=[{'name': 'Color', 'value': 'red'}])
        no_asin = catalog.create_product(description='Hand-entered thing')

        for product in (filled, no_asin):
            html = client.get(f'/products/{product.id}').get_data(as_text=True)
            assert 'id="details-missing-notice"' not in html

    def test_the_review_no_longer_makes_the_old_promise(self, client):
        """FR-021: the note says what the code does."""
        order = build_order()
        response = client.post('/api/capture', data={
            'url': order.source_url,
            'listing': json.dumps({'version': 1, 'source_url': order.source_url}),
            'order': json.dumps({
                'version': AMAZON_PAYLOAD_VERSION,
                'vendor': AMAZON_PAYLOAD_VENDOR,
                'order_number': ORDER_NUMBER,
                'order_date': ORDER_DATE_TEXT,
                'source_url': order.source_url,
                'lines': [{'asin': ASIN, 'title': 'M3 Socket Head Cap Screws',
                           'quantity': 1, 'unit_price': '8.99'}],
            }),
            'vendor': AMAZON_VENDOR,
        })

        html = response.get_data(as_text=True)
        assert 'id="order-page-detail-note"' in html
        assert 'recognizes the purchase this order recorded' not in html
        assert 'without recording another' in html


def order_payload(lines, order_date=ORDER_DATE_TEXT):
    """The hidden `order` field, as the agent sends it and the review carries it."""
    return json.dumps({
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': ORDER_NUMBER,
        'order_date': order_date,
        'source_url': (
            'https://www.amazon.com/your-orders/order-details'
            f'?orderID={ORDER_NUMBER}'
        ),
        'lines': lines,
    })


def order_line(asin=ASIN, title='M3 Socket Head Cap Screws', **extra):
    line = {'asin': asin, 'title': title, 'quantity': 1, 'unit_price': '8.99'}
    line.update(extra)
    return line


def confirm_order(client, lines, follow_redirects=False):
    """Confirm an order's review with every line included, as it defaults."""
    data = {'order': order_payload(lines)}
    for number in range(1, len(lines) + 1):
        data[f'include[{number}]'] = 'on'
    return client.post(
        '/products/amazon/orders/capture', data=data,
        follow_redirects=follow_redirects,
    )


class TestTheOrderPayloadCarriesListings:
    """T027: a line's listing, parsed; what the capture reports about lines."""

    def test_a_line_carries_its_listing(self):
        line = AmazonOrderLine.from_payload(order_line(listing=listing_payload()), 0)

        assert line.listing.brand == 'Acme Fasteners'
        assert line.listing_problem == ''

    def test_a_line_carries_why_it_was_not_read(self):
        line = AmazonOrderLine.from_payload(order_line(
            listing_problem='the listing could not be fetched (HTTP 503)',
        ), 0)

        assert line.listing is None
        assert line.listing_problem == 'the listing could not be fetched (HTTP 503)'

    def test_an_unusable_listing_costs_the_listing_not_the_line(self):
        line = AmazonOrderLine.from_payload(order_line(listing={'version': 99}), 0)

        assert line is not None
        assert line.listing is None
        assert line.listing_problem == 'the listing read was unusable'

    def test_an_older_agents_line_is_unchanged(self):
        line = AmazonOrderLine.from_payload(order_line(), 0)

        assert line.listing is None
        assert line.listing_problem == ''
        hash(line)

    def test_the_order_counts_what_was_read(self):
        order = AmazonOrder.from_payload(json.loads(order_payload([
            order_line(listing=listing_payload()),
            order_line(asin=SECOND_ASIN, listing_problem='nope'),
            order_line(asin='B0CXYZ9999'),
        ])))

        assert order.listings_read == 1
        assert order.listings_unread == 1

    def test_each_written_or_already_captured_line_names_its_product(self, catalog):
        order = build_order(lines=[order_line(), order_line(asin=SECOND_ASIN)])
        first = catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
            '1': {'include': True}, '2': {'include': False},
        })
        product_id = dict(first.line_products)['1']
        assert set(dict(first.line_products)) == {'1'}

        again = catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
            '1': {}, '2': {'include': True},
        })

        assert dict(again.line_products)['1'] == product_id
        assert '2' in dict(again.line_products)

    def test_details_alone_count_as_a_write(self):
        assert OrderCaptureResult(products_detailed=1).wrote_anything is True
        assert OrderCaptureResult().wrote_anything is False


@pytest.fixture
def stored_images():
    with patch(
        'app.product.routes.store_listing_images',
        return_value=ImageCaptureResult(stored=1),
    ) as stored:
        yield stored


class TestConfirmingAnOrderWithListings:
    """T028: US4 -- one order capture carries every line's details."""

    def only_product_on_the_order(self, catalog):
        lines = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)
        assert len(lines) == 1
        return lines[0].product_id

    def test_a_new_product_carries_its_listing(self, catalog, client, stored_images):
        """FR-026"""
        response = confirm_order(client, [order_line(listing=listing_payload())])

        assert response.status_code == 302
        product_id = self.only_product_on_the_order(catalog)
        product = catalog.get_product(product_id)
        assert product.manufacturer == 'Acme Fasteners'
        assert 'Thread Size' in spec_rows(catalog, product_id)
        assert len(catalog.get_purchase_history(product_id)) == 1

    def test_a_product_already_in_the_catalog_only_gains_what_it_lacks(
        self, catalog, client, stored_images
    ):
        """FR-027"""
        existing = thin_product(catalog, manufacturer='Held Co')

        confirm_order(client, [order_line(listing=listing_payload())])

        assert catalog.get_product(existing.id).manufacturer == 'Held Co'
        assert 'Thread Size' in spec_rows(catalog, existing.id)

    def test_a_line_not_read_stays_thin_and_reads_as_missing(
        self, catalog, client, stored_images
    ):
        """FR-028"""
        confirm_order(client, [order_line(listing_problem='HTTP 503')])

        product_id = self.only_product_on_the_order(catalog)
        assert catalog.products_missing_details([product_id]) == {product_id}
        stored_images.assert_not_called()

    def test_two_lines_naming_one_item_are_filled_once(
        self, catalog, client, stored_images
    ):
        payload = listing_payload(images=['https://m.media-amazon.com/images/I/a.jpg'])

        confirm_order(client, [
            order_line(listing=payload),
            order_line(listing=payload, quantity=2),
        ])

        assert stored_images.call_count == 1

    def test_recapturing_an_order_fills_in_what_it_created(
        self, catalog, client, stored_images
    ):
        """FR-030: the one-click repair for an order captured before 044."""
        recorded = capture_the_order(catalog)

        response = confirm_order(
            client, [order_line(listing=listing_payload())], follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        assert 'Details added to 1 product(s)' in html
        assert 'Nothing new to capture' not in html
        assert 'Thread Size' in spec_rows(catalog, recorded.product_id)
        assert len(catalog.get_purchase_history(recorded.product_id)) == 1

    def test_the_review_shows_what_each_listing_yielded(self, client):
        """FR-024, FR-025"""
        source = 'https://www.amazon.com/your-orders/order-details'
        response = client.post('/api/capture', data={
            'url': source,
            'listing': json.dumps({'version': 1, 'source_url': source}),
            'vendor': AMAZON_VENDOR,
            'order': order_payload([
                order_line(listing=listing_payload()),
                order_line(
                    asin=SECOND_ASIN, title='PLA Filament',
                    listing_problem='the page was not a listing',
                ),
            ]),
        })

        html = response.get_data(as_text=True)
        assert 'line-listing-summary' in html
        assert 'Acme Fasteners' in html
        assert 'details-not-read' in html
        assert 'the page was not a listing' in html
        assert 'data-listings-read="1"' in html
        assert 'data-listings-missing="1"' in html
