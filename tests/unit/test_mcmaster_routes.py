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
