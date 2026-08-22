"""
E2E tests for capturing a DigiKey order (feature 024, US1).

**DigiKey is played by a loopback HTTP server** serving the responses recorded
off the live API on 2026-08-22 and redacted. The application's own
``DigiKeyClient`` is pointed at it through ``DIGIKEY_API_BASE``, so the token
exchange, the ``X-DIGIKEY-Account-ID`` header, the JSON parsing and the
``Decimal`` prices are all exercised for real -- only the far end is fake. This
is the same shape ``test_product_page_capture.py`` uses to play Amazon's image
host, and it is why ``DIGIKEY_API_BASE`` is configurable at all.

Waiting rules (Constitution IV): every page here is server-rendered, so
``expect(rows).to_have_count(n)`` is a complete signal. The one place that is
not is the capture confirmation, which does network work before it redirects --
there the wait is on the order screen's own content, never on the button.
"""

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'
SALES_ORDER = '100882558'

# The parts the recorded order contains, in both their spellings. Anything else
# the fake answers 404 for, so FR-032 is testable.
KNOWN_PARTS = ('1866-3027-ND', '1866-3032-ND', 'IRM-05-5', 'IRM-10-5')


class _DigiKeyHandler(BaseHTTPRequestHandler):
    """Three routes: a token, an order, a part.

    Records the headers it was sent so a test can assert the account header
    actually went out -- the thing whose absence answers 400 in production.
    """

    seen_headers = []

    def log_message(self, *args):  # keep the suite's output readable
        pass

    def _send(self, status, body):
        payload = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path.endswith('/oauth2/token'):
            self._send(200, json.dumps({
                'access_token': 'e2e-token', 'token_type': 'Bearer', 'expires_in': 599
            }))
        else:
            self._send(404, '{}')

    def do_GET(self):
        type(self).seen_headers.append(dict(self.headers))
        if '/orderstatus/v4/salesorder/' in self.path:
            if self.path.rstrip('/').endswith(SALES_ORDER):
                self._send(200, (FIXTURES / 'salesorder.json').read_text())
            else:
                self._send(404, '{"detail": "no such order"}')
        elif '/productdetails' in self.path:
            # Only the parts this order actually contains. Serving the fixture
            # for any path at all would make it impossible to test what happens
            # when DigiKey does not know a part number (FR-032).
            if any(known in self.path for known in KNOWN_PARTS):
                self._send(200, (FIXTURES / 'productdetails.json').read_text())
            else:
                self._send(404, '{"detail": "no such product"}')
        else:
            self._send(404, '{}')


@pytest.fixture
def digikey_api(live_server):
    """Stand DigiKey up on loopback and point the running app at it.

    The app is session-scoped, so the previous client is put back afterwards --
    a test that leaves the application pointing at a dead port would fail every
    test after it, somewhere unrelated.
    """
    from app.services.digikey import DigiKeyClient

    _DigiKeyHandler.seen_headers = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), _DigiKeyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    previous = live_server.app.config.get('DIGIKEY_CLIENT')
    live_server.app.config['DIGIKEY_CLIENT'] = DigiKeyClient(
        client_id='e2e-client',
        client_secret='e2e-secret',
        account_id='99999999',
        base_url=f'http://127.0.0.1:{server.server_port}',
    )
    try:
        yield server
    finally:
        live_server.app.config['DIGIKEY_CLIENT'] = previous
        server.shutdown()
        server.server_close()


def review_order(page, live_server, number=SALES_ORDER):
    """Enter a sales order number and land on the review."""
    page.goto(f"{live_server.url}/products/digikey/orders")
    page.fill('#sales_order_number', number)
    page.click('#review-order')
    return page


@pytest.mark.e2e
def test_the_review_lists_every_line_and_writes_nothing(page, live_server, digikey_api):
    """FR-003, FR-004."""
    review_order(page, live_server)

    # Server-rendered, so the row count is a complete signal.
    expect(page.locator('.order-line')).to_have_count(2)
    expect(page.locator('#review-banner')).to_contain_text('Nothing has been recorded yet')

    # Both lines, with what the order gave.
    expect(page.locator('.order-line[data-part="1866-3027-ND"]')).to_contain_text('IRM-05-5')
    expect(page.locator('.order-line[data-part="1866-3032-ND"]')).to_contain_text('IRM-10-5')

    # And nothing exists yet. Establish the region before reading it: an empty
    # product list would satisfy this trivially against a page that had not
    # loaded.
    page.goto(f"{live_server.url}/products")
    expect(page.locator('h2')).to_contain_text('Products')
    expect(page.get_by_text('AC/DC CONVERTER 5V 5W')).to_have_count(0)


@pytest.mark.e2e
def test_every_line_is_enriched_from_digikey(page, live_server, digikey_api):
    """FR-040: the manufacturer is not on an order line, so it came from the part call."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    expect(page.locator('.order-line').first).to_contain_text('MEAN WELL USA Inc.')


@pytest.mark.e2e
def test_the_account_header_is_sent(page, live_server, digikey_api):
    """Without it DigiKey answers 400; the E2E fake is the only place we can see it go out."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)

    order_calls = [h for h in _DigiKeyHandler.seen_headers if h.get('X-DIGIKEY-Account-ID')]
    assert order_calls, 'no request carried X-DIGIKEY-Account-ID'
    assert order_calls[0]['X-DIGIKEY-Account-ID'] == '99999999'
    assert order_calls[0]['Authorization'] == 'Bearer e2e-token'


@pytest.mark.e2e
def test_confirming_creates_one_outstanding_purchase_per_line(page, live_server, digikey_api):
    """FR-008, SC-002."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    page.fill('.order-line[data-part="1866-3027-ND"] .line-description', '5V 5W brick')

    page.click('#confirm-capture')

    # The confirmation re-reads the order and every part before redirecting, so
    # the button returning says nothing. Wait for the order screen's own content.
    expect(page.locator('#order-progress')).to_contain_text('2 of 2 still outstanding')
    expect(page.locator('.order-line')).to_have_count(2)
    expect(page.locator('.order-line[data-outstanding="true"]')).to_have_count(2)
    expect(page.get_by_text('5V 5W brick')).to_be_visible()


@pytest.mark.e2e
def test_an_excluded_line_writes_nothing(page, live_server, digikey_api):
    """FR-007."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    page.uncheck('#include-1866-3027-ND')
    page.click('#confirm-capture')

    expect(page.locator('#order-progress')).to_contain_text('1 of 1 still outstanding')
    expect(page.locator('.order-line[data-part="1866-3027-ND"]')).to_have_count(0)
    expect(page.locator('.order-line[data-part="1866-3032-ND"]')).to_have_count(1)


@pytest.mark.e2e
def test_recapturing_records_nothing_new(page, live_server, digikey_api):
    """FR-012, SC-003. A sales order number is exact, not a same-day guess."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    page.click('#confirm-capture')
    expect(page.locator('#order-progress')).to_contain_text('2 of 2 still outstanding')

    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    # Both already captured, so nothing is offered for capture.
    expect(page.locator('.order-line[data-state="CAPTURED"]')).to_have_count(2)

    page.click('#confirm-capture')
    expect(page.locator('#order-progress')).to_contain_text('2 of 2 still outstanding')
    expect(page.locator('.order-line')).to_have_count(2)


@pytest.mark.e2e
def test_a_line_already_in_the_catalog_attaches_rather_than_duplicating(
        page, live_server, digikey_api):
    """FR-005, SC-005."""
    from app.catalog_service import CatalogService

    CatalogService(live_server.storage).create_product(
        description='5V PSU I already own',
        identifiers=[{'id_type': 'MPN', 'value': 'IRM-05-5'}],
    )

    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    expect(page.locator('.order-line[data-state="MATCHED"]')).to_have_count(1)
    expect(page.locator('.order-line[data-part="1866-3027-ND"]')).to_contain_text(
        '5V PSU I already own'
    )

    page.click('#confirm-capture')
    expect(page.locator('#order-progress')).to_contain_text('2 of 2 still outstanding')

    # One product for that part, not two.
    page.goto(f"{live_server.url}/products?q=IRM-05-5")
    expect(page.locator('h2')).to_contain_text('Products')
    expect(page.get_by_text('5V PSU I already own')).to_have_count(1)


@pytest.mark.e2e
def test_an_uncaptured_order_says_so_rather_than_404(page, live_server, digikey_api):
    page.goto(f"{live_server.url}/products/digikey/orders/999999999")
    expect(page.locator('#not-captured')).to_be_visible()


@pytest.mark.e2e
def test_an_unknown_order_number_is_reported_not_an_error_page(page, live_server, digikey_api):
    """FR-038: the operator's next action is to retype, so this is a message, not a 500."""
    review_order(page, live_server, number='999999999')
    expect(page.locator('#digikey-not-found')).to_be_visible()
    # And the form is still there to retype into.
    expect(page.locator('#sales_order_number')).to_have_value('999999999')


@pytest.mark.e2e
def test_without_digikey_configured_the_page_says_so(page, live_server):
    """FR-036, FR-037. No digikey_api fixture: the client is whatever the app has."""
    previous = live_server.app.config.get('DIGIKEY_CLIENT')
    live_server.app.config['DIGIKEY_CLIENT'] = None
    try:
        page.goto(f"{live_server.url}/products/digikey/orders")
        expect(page.locator('#digikey-not-configured')).to_be_visible()

        # And the rest of the catalog is untouched.
        page.goto(f"{live_server.url}/products")
        expect(page.locator('h2')).to_contain_text('Products')
    finally:
        live_server.app.config['DIGIKEY_CLIENT'] = previous
