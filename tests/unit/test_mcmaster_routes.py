"""The McMaster capture routes, end to end through the test client.

Three of them, and the seam between them is FR-006:

* ``POST /api/capture`` with an ``order`` field renders the review and
  **writes nothing**;
* ``POST /products/mcmaster/orders/capture`` writes what the review carried;
* ``GET /products/mcmaster/orders/<order_number>`` renders it back.

The payload riding through the review in a hidden field is the whole mechanism.
DigiKey's confirm step re-fetches its order and treats that as the authority;
there is nothing here to re-fetch, so if the field is lost the capture is lost.
"""

import json
import re

import pytest

pytestmark = pytest.mark.unit

SOURCE_URL = ('https://www.mcmaster.com/order-history/order/'
              '6a5ffba81f17e12ac4fb7d70')

PAYLOAD = {
    'version': 1,
    'vendor': 'McMaster-Carr',
    'source_url': SOURCE_URL,
    'order_number': 'MISC-AND-GRINDER',
    'order_id': '6a5ffba81f17e12ac4fb7d70',
    'order_date': 'November 16, 2025',
    # Three seen, two readable -- so the FR-004 tally has something to say.
    'lines_read': 3,
    'lines': [
        {'line_number': 1, 'part_number': '3103A21',
         'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23'},
        {'line_number': 5, 'part_number': '97387A173',
         'description': 'Rivets', 'packs': 1, 'pack_size': 100,
         'pack_price': '6.66'},
    ],
}


def post_capture(client, order=None, **extra):
    data = {'url': SOURCE_URL, 'listing': '', 'vendor': 'McMaster-Carr'}
    if order is not None:
        data['order'] = json.dumps(order)
    data.update(extra)
    return client.post('/api/capture', data=data)


def carried_payload(html):
    """The payload the review is carrying, unescaped."""
    match = re.search(r'name="order" id="order-payload" value="([^"]*)"', html)
    assert match, 'the review did not carry the payload through'
    raw = match.group(1)
    for entity, char in (('&#34;', '"'), ('&amp;', '&'), ('&lt;', '<'),
                         ('&gt;', '>'), ('&#39;', "'")):
        raw = raw.replace(entity, char)
    return raw


class TestReview:

    def test_an_order_payload_renders_the_review(self, client):
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        assert 'MISC-AND-GRINDER' in html
        assert 'order-lines' in html
        assert '3103A21' in html and '97387A173' in html

    def test_the_review_writes_nothing(self, client):
        """FR-005."""
        post_capture(client, PAYLOAD)

        html = client.get(
            '/products/mcmaster/orders/MISC-AND-GRINDER'
        ).get_data(as_text=True)
        assert 'not-captured' in html

    def test_the_payload_is_carried_through(self, client):
        """FR-004: "three of your fifteen" must not read as "three"."""
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        assert json.loads(carried_payload(html)) == PAYLOAD

    def test_the_line_tally_names_what_could_not_be_read(self, client):
        """FR-004: "three of your fifteen" must not look like "three"."""
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        assert 'Only 2 of the 3' in html
        assert 'incomplete-warning' in html

    def test_a_fully_read_order_says_nothing_about_a_tally(self, client):
        body = dict(PAYLOAD, lines_read=2)

        html = post_capture(client, body).get_data(as_text=True)

        assert 'incomplete-warning' not in html
        assert '2 line(s) ordered' in html

    def test_a_payload_naming_no_order_states_so(self, client):
        """FR-038. Never an error page."""
        html = post_capture(
            client, {'version': 99, 'vendor': 'McMaster-Carr'}
        ).get_data(as_text=True)

        assert 'no-order' in html

    def test_an_order_with_no_readable_lines_is_not_an_empty_order(
            self, client):
        """FR-038's other half."""
        body = dict(PAYLOAD, lines=[], lines_read=15)

        html = post_capture(client, body).get_data(as_text=True)

        assert 'no-lines' in html
        assert 'MISC-AND-GRINDER' in html

    def test_a_request_with_no_order_field_takes_todays_path(self, client):
        """The SC-010 boundary, asserted here as well as by the e2e suite."""
        resp = client.post('/api/capture', data={
            'url': 'https://www.amazon.com/dp/B08N5WRWNW',
            'listing_title': 'A thing', 'listing': '',
        })

        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'B08N5WRWNW' in html
        assert 'order-lines' not in html


class TestConfirm:

    def confirm(self, client, html, **overrides):
        data = {
            'order': carried_payload(html),
            'include[1]': 'on', 'include[5]': 'on',
            'description[1]': 'Counterbore pilot',
            'description[5]': 'Rivets, stainless',
            'quantity[1]': '1', 'quantity[5]': '100',
            'unit_price[1]': '10.23', 'unit_price[5]': '0.07',
        }
        data.update(overrides)
        return client.post('/products/mcmaster/orders/capture', data=data,
                           follow_redirects=True)

    def test_confirming_writes_and_lands_on_the_order(self, client):
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        landed = self.confirm(client, html).get_data(as_text=True)

        assert 'Captured 2 line(s)' in landed
        assert '2 of 2 still outstanding' in landed
        assert '3103A21' in landed and '97387A173' in landed

    def test_an_excluded_line_writes_nothing(self, client):
        """FR-009."""
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        landed = self.confirm(
            client, html, **{'include[5]': None}
        ).get_data(as_text=True)

        assert 'Captured 1 line(s)' in landed
        assert '1 skipped' in landed
        assert '97387A173' not in landed

    def test_a_second_capture_records_nothing(self, client):
        """SC-003."""
        html = post_capture(client, PAYLOAD).get_data(as_text=True)
        self.confirm(client, html)

        again = post_capture(client, PAYLOAD).get_data(as_text=True)

        assert 'already captured' in again

    def test_a_refused_description_re_renders_carrying_what_was_typed(
            self, client):
        """The operator's authored description must survive the refusal."""
        html = post_capture(client, PAYLOAD).get_data(as_text=True)

        resp = self.confirm(
            client, html, **{'description[1]': 'x' * 400})

        body = resp.get_data(as_text=True)
        assert 'order-lines' in body, 'the review was not re-rendered'
        assert 'Rivets, stainless' in body, (
            'a description the operator typed was lost on the refusal'
        )
        # Nothing was written.
        assert 'not-captured' in client.get(
            '/products/mcmaster/orders/MISC-AND-GRINDER'
        ).get_data(as_text=True)

    def test_an_unreadable_payload_on_confirm_states_so(self, client):
        resp = client.post('/products/mcmaster/orders/capture',
                           data={'order': 'not json at all'})

        assert resp.status_code == 200
        assert 'no-order' in resp.get_data(as_text=True)


class TestOrderScreen:

    def test_an_order_nothing_was_captured_against_is_not_a_404(self, client):
        """FR-031. Nothing dead-ends."""
        resp = client.get('/products/mcmaster/orders/NOTHING-HERE')

        assert resp.status_code == 200
        assert 'not-captured' in resp.get_data(as_text=True)

    def test_highlight_marks_a_line(self, client):
        html = post_capture(client, PAYLOAD).get_data(as_text=True)
        TestConfirm().confirm(client, html)

        resp = client.get(
            '/products/mcmaster/orders/MISC-AND-GRINDER?highlight=3103A21')

        body = resp.get_data(as_text=True)
        assert 'table-active' in body


class TestPartNumberFromUrl:
    """FR-025: the paste-a-URL path, with no agent involved at all.

    The pattern is deliberately duplicated between the agent and the server --
    they are on opposite sides of a machine boundary, the agent's copy decides
    which reader runs, and this one is what the form uses. The Amazon pair
    carries the same note.
    """

    @pytest.mark.parametrize('url, expected', [
        ('https://www.mcmaster.com/91290A115/', '91290A115'),
        ('https://mcmaster.com/91290A115/', '91290A115'),
        ('https://www.mcmaster.com/91290A115', '91290A115'),
        ('https://www.mcmaster.com/2652N1/', '2652N1'),
        ('https://www.mcmaster.com/27465A236/', '27465A236'),
        ('https://www.mcmaster.com/3103A2/', '3103A2'),
        # Matched on the path, never the host -- as _asin_from_url is, and for
        # the same reason: the e2e harness serves the fixture from this app's
        # own origin, so a host gate would leave it with no coverage.
        ('http://127.0.0.1:8080/91290A115/', '91290A115'),
    ])
    def test_a_product_page_yields_its_part_number(self, url, expected):
        from app.product.routes import _mcmaster_part_from_url

        assert _mcmaster_part_from_url(url) == expected

    @pytest.mark.parametrize('url', [
        'https://www.amazon.com/dp/B08N5WRWNW',
        'https://www.mcmaster.com/',
        'https://www.mcmaster.com',
        '',
        'not a url at all',
        # The family table /catalog/<part> redirects to. It names many part
        # numbers rather than one product, so it must not yield one.
        'https://www.mcmaster.com/products/97531a492/',
        # The order list, and one order.
        'https://www.mcmaster.com/order-history/',
        'https://www.mcmaster.com/order-history/order/6a5ffba81f17e12ac4fb7d70',
    ])
    def test_anything_else_is_blank_rather_than_an_error(self, url):
        """Blank is the ordinary answer -- the operator fills it in."""
        from app.product.routes import _mcmaster_part_from_url

        assert _mcmaster_part_from_url(url) == ''

    def test_a_pasted_url_fills_the_vendor_and_the_part(self, client):
        """FR-025, through the form the operator actually uses."""
        resp = client.post('/products/capture', data={
            'url': 'https://www.mcmaster.com/91290A115/',
            'description': 'Socket head screw, M3 x 10',
            'quantity': '100',
            'unit_price': '0.13',
        }, follow_redirects=True)

        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '91290A115' in html


class TestProductCaptureIdentifiers:
    """US2 scenario 2, and the defect it turns out to guard.

    The scenario asks for the part number as a `DISTRIBUTOR` identifier scoped
    to McMaster-Carr, "so that scanning or searching that number finds it".
    What the product-page path actually writes is `VENDOR`, scoped the same way
    -- ``capture_order`` has written that for every vendor since feature 007,
    and it is the path every Amazon capture goes through.

    Both types are vendor-scoped and both are in ``VENDOR_SCOPED_TYPES``, so
    the *stated purpose* holds either way: a scan finds it. Editing that shared
    write path to emit a different type for one vendor was rejected -- SC-010
    requires it to behave identically after this feature.

    What genuinely had to be fixed is the other side: the order review looks up
    **both** types, so an order capture recognizes a part already catalogued
    from its product page instead of creating a second product for it.
    """

    def capture_the_product_page(self, client):
        from app.catalog_service import MCMASTER_VENDOR

        return client.post('/products/capture', data={
            'url': 'https://www.mcmaster.com/91290A115/',
            'vendor': MCMASTER_VENDOR,
            'description': 'Socket head screw, M3 x 10',
            'quantity': '100',
            'unit_price': '0.13',
        }, follow_redirects=True)

    def test_the_part_number_is_recorded_scoped_to_mcmaster(self, client, app):
        from app.catalog_service import (
            CatalogService, MCMASTER_VENDOR, VENDOR_SCOPED_TYPES,
        )

        self.capture_the_product_page(client)

        catalog = CatalogService(app.config['STORAGE_BACKEND'])
        product = catalog.find_product_by_identifier(
            '91290A115', id_type='VENDOR', vendor=MCMASTER_VENDOR)

        assert product is not None, 'the part number was not recorded at all'
        scoped = [
            i for i in product.identifiers
            if i.value == '91290A115'
        ]
        assert scoped, 'no identifier carries the part number'
        assert all(i.vendor == MCMASTER_VENDOR for i in scoped), (
            'the identifier was not scoped to McMaster-Carr'
        )
        assert all(
            i.id_type in {t.value for t in VENDOR_SCOPED_TYPES}
            for i in scoped
        ), 'the identifier is not of a vendor-scoped kind, so a scan misses it'

    def test_no_mpn_is_invented_for_a_page_that_named_no_manufacturer(
            self, client, app):
        """Inventing an identifier McMaster never stated would collide with a
        real MPN later, and identifiers are unique."""
        from app.catalog_service import CatalogService, MCMASTER_VENDOR
        from app.models import IdentifierType

        self.capture_the_product_page(client)

        catalog = CatalogService(app.config['STORAGE_BACKEND'])
        product = catalog.find_product_by_identifier(
            '91290A115', id_type='VENDOR', vendor=MCMASTER_VENDOR)

        assert not [
            i for i in product.identifiers
            if i.id_type == IdentifierType.MPN.value
        ]

    def test_an_order_capture_finds_a_part_catalogued_from_its_product_page(
            self, client, app):
        """The defect this guards. Looking up only DISTRIBUTOR would read this
        line as NEW and create a second product for a part already held."""
        import json as _json
        from app.catalog_service import CatalogService, MCMASTER_VENDOR

        self.capture_the_product_page(client)

        body = dict(PAYLOAD, lines=[{
            'line_number': 1, 'part_number': '91290A115',
            'description': 'Socket head screws', 'packs': 1,
            'pack_size': 100, 'pack_price': '13.23',
        }], lines_read=1)
        html = client.post('/api/capture', data={
            'url': SOURCE_URL, 'listing': '', 'vendor': MCMASTER_VENDOR,
            'order': _json.dumps(body),
        }).get_data(as_text=True)

        assert 'data-state="MATCHED"' in html, (
            'the order did not recognize a part already in the catalog'
        )

        client.post('/products/mcmaster/orders/capture', data={
            'order': carried_payload(html), 'include[1]': 'on',
            'quantity[1]': '100', 'unit_price[1]': '0.13',
        }, follow_redirects=True)

        catalog = CatalogService(app.config['STORAGE_BACKEND'])
        holders = [
            p for p in catalog.list_products()
            if any(i.value == '91290A115' for i in p.identifiers)
        ]
        assert len(holders) == 1, (
            f'{len(holders)} products now carry 91290A115; the order capture '
            f'created a duplicate'
        )
