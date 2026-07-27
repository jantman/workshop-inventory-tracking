"""
E2E tests for scan outcome routing (Story 4.5, FR36/FR39/FR40/FR41).

The whole identification loop, driven through the browser exactly as the
operator drives it: a wedge scan into the global navbar field, and wherever the
server says it goes. Story 4.1's e2e file covers the CAPTURE half (what is
posted, what happens to the field, what a failure does); this one covers the
LANDING half — the four destinations a scan can reach and what the operator can
do when they get there.

Every scenario below runs against the real server and real seeded data. Nothing
is stubbed: the point of these tests is that the classifier, the resolver, the
route's destination mapping, the template and the one line of client navigation
agree end to end, and a stub anywhere in that chain would be the one link not
being tested.

Isolation note: the e2e server's ``clear_test_data()`` truncates the catalog
tables (``products``, ``purchases``, ``attachments``, ``product_identifiers``,
``product_tags``) along with photos and inventory items (and re-seeds the
material taxonomy rather than leaving it empty), and ``live_server`` is
function-scoped, so every test — and every ``--reruns``
replay, which re-runs setup — starts from an empty catalog.

The per-invocation minting below (a random check-digit-valid GTIN, a
uuid-bearing description or part number) is kept anyway. It costs nothing, and
"empty at setup" is not "empty here": by the time a test asserts, the catalog
holds that test's own rows. So assertions stay positive/containment ones, and
an absence assertion is allowed only where the text it looks for carries the
run-unique token.
"""

import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import SCAN_INPUT, simulate_wedge_scan, unstored_gtin


def _token(label):
    """A string no other test, run or rerun can have created."""
    return f'e2escan-{label}-{uuid.uuid4().hex[:8]}'


def _envelope(*records):
    """An ISO/IEC 15434 format-06 message carrying `records` verbatim."""
    return '[)>\x1e06' + ''.join(f'\x1d{record}' for record in records) + '\x1d\x1e\x04'


def _scan_raw(page, text):
    """Scan text a keyboard cannot type.

    A browser will not insert GS/RS into an `<input type="text">` from
    keystrokes, so an ISO/IEC 15434 envelope has to be placed in the field
    directly — but the terminator is still a real key press, which is what
    actually drives the capture path. Same technique as
    `test_server_echo_matches_the_clients_own_trim_rule`.
    """
    page.evaluate("""(v) => {
        const el = document.getElementById('scan-input');
        el.focus();
        el.value = v;
    }""", text)
    page.locator(SCAN_INPUT).press('Enter')


def _create_product(page, live_server, description, query=''):
    """Create a product through the real create form; return its detail URL.

    `query` lets a test open the form the way a scan would, so the seeded
    product carries whatever that pre-fill implies (an identifier, say).
    """
    page.goto(f'{live_server.url}/products/add{query}')
    expect(page.locator('#description')).to_be_visible(timeout=10000)
    page.locator('#description').fill(description)
    page.locator('button[type="submit"]').click()
    expect(page.locator('body')).to_contain_text(description, timeout=10000)
    return page.url


@pytest.mark.e2e
class TestScanLandsOnAProduct:
    """FR36: a match lands on the record, with the receiving-context banner."""

    def test_a_matching_gtin_lands_on_the_product_showing_the_banner(
            self, page, live_server):
        gtin = unstored_gtin(live_server)
        description = f'Scan routing GTIN product {_token("gtin")}'

        # Seeded through the same pre-filled form a scan would have opened, so
        # the identifier attach path is what put the GTIN in the catalog.
        detail_url = _create_product(
            page, live_server, description,
            query=f'?identifier_type=GTIN&identifier_value={gtin}')

        page.goto(f'{live_server.url}/')
        simulate_wedge_scan(page, gtin)

        page.wait_for_url('**/products/**', timeout=10000)
        assert page.url.split('?')[0] == detail_url.split('?')[0]
        expect(page.locator('#scan-banner')).to_be_visible(timeout=10000)
        expect(page.locator('body')).to_contain_text(description)
        # Both affordances FR41 names.
        expect(page.locator('#scan-banner-purchase')).to_be_visible()
        expect(page.locator('#scan-banner-create')).to_be_visible()

    def test_the_banner_leads_to_a_purchase_the_product_then_shows(
            self, page, live_server):
        """FR41: a scan resolving to an existing Product in a receiving context
        offers to add a Purchase to that Product."""
        gtin = unstored_gtin(live_server)
        order_number = _token('po').upper()
        description = f'Scan routing receipt product {_token("receipt")}'

        _create_product(page, live_server, description,
                        query=f'?identifier_type=GTIN&identifier_value={gtin}')

        page.goto(f'{live_server.url}/')
        simulate_wedge_scan(page, gtin)
        expect(page.locator('#scan-banner')).to_be_visible(timeout=10000)

        page.locator('#scan-banner-purchase').click()
        page.wait_for_url('**/purchases/add**', timeout=10000)
        page.locator('#vendor').fill('DigiKey')
        page.locator('#order_number').fill(order_number)
        page.locator('#quantity').fill('100')
        page.locator('button[type="submit"]').click()

        # Back on the product, with the purchase in its history.
        page.wait_for_url('**/products/**', timeout=10000)
        expect(page.locator('body')).to_contain_text('DigiKey', timeout=10000)
        expect(page.locator('body')).to_contain_text(description)


@pytest.mark.e2e
class TestScanLandsOnACreateForm:
    """FR40: a scan matching nothing opens a create form — never an error."""

    def test_an_unmatched_gtin_prefills_the_identifier_editably(
            self, page, live_server):
        gtin = unstored_gtin(live_server)
        page.goto(f'{live_server.url}/')

        simulate_wedge_scan(page, gtin)

        page.wait_for_url('**/products/add**', timeout=10000)
        identifier = page.locator('#identifier_value')
        # The canonical 14-digit key, which is the namespace lookup runs in.
        expect(identifier).to_have_value(f'0{gtin}', timeout=10000)
        expect(identifier).to_be_editable()
        expect(page.locator('#identifier_type')).to_have_value('GTIN')
        # Nothing is submitted here: an unmatched scan must not create anything
        # by arriving, and leaving the catalog untouched keeps this GTIN
        # unmatched for the next run too.

    def test_an_ecia_envelope_prefills_mpn_quantity_and_order_references(
            self, page, live_server):
        """FR39: a parsed distributor scan with no matching product opens the
        create form with MPN, quantity and order references pre-filled, and
        every pre-filled value stays editable."""
        supplier_pn = _token('sup').upper()
        customer_pn = _token('cust').upper()
        order_number = _token('ord').upper()

        page.goto(f'{live_server.url}/')
        _scan_raw(page, _envelope(f'1P{supplier_pn}', f'P{customer_pn}',
                                  'Q42', f'K{order_number}'))

        page.wait_for_url('**/products/add**', timeout=10000)
        expect(page.locator('#mpn')).to_have_value(supplier_pn, timeout=10000)
        expect(page.locator('#vendor_sku')).to_have_value(customer_pn)
        expect(page.locator('#quantity')).to_have_value('42')
        expect(page.locator('#order_number')).to_have_value(order_number)
        for field in ('#mpn', '#vendor_sku', '#quantity', '#order_number'):
            expect(page.locator(field)).to_be_editable()

    def test_free_text_matching_nothing_keeps_the_scan_in_the_description(
            self, page, live_server):
        scanned = _token('freetext').upper()
        page.goto(f'{live_server.url}/')

        simulate_wedge_scan(page, scanned)

        page.wait_for_url('**/products/add**', timeout=10000)
        expect(page.locator('#description')).to_have_value(scanned, timeout=10000)


@pytest.mark.e2e
class TestScanLandsOnSearchResults:
    """FR36: an ambiguous scan lands on a list, within the same scan."""

    def test_text_matching_several_products_lands_on_the_search_page(
            self, page, live_server):
        shared = _token('hits').upper()
        first = f'Scan routing hit A {shared}'
        second = f'Scan routing hit B {shared}'
        _create_product(page, live_server, first)
        _create_product(page, live_server, second)

        page.goto(f'{live_server.url}/')
        simulate_wedge_scan(page, shared)

        page.wait_for_url('**/products/search**', timeout=10000)
        expect(page.locator('#search-query')).to_have_text(shared, timeout=10000)
        table = page.locator('#search-result-table')
        expect(table).to_contain_text(first)
        expect(table).to_contain_text(second)
        # A search landing does not dead-end either.
        expect(page.locator('#search-create-product')).to_be_visible()


@pytest.mark.e2e
class TestDuplicateConfirmationInTheBrowser:
    """FR41: creating a duplicate Product instead requires an explicit
    confirmation, and it is not possible to reach the write without one."""

    def test_the_gate_refuses_until_the_operator_confirms(self, page, live_server):
        gtin = unstored_gtin(live_server)
        original = f'Scan routing original {_token("orig")}'
        duplicate = f'Scan routing duplicate {_token("dup")}'

        _create_product(page, live_server, original,
                        query=f'?identifier_type=GTIN&identifier_value={gtin}')

        page.goto(f'{live_server.url}/')
        simulate_wedge_scan(page, gtin)
        expect(page.locator('#scan-banner')).to_be_visible(timeout=10000)

        page.locator('#scan-banner-create').click()
        page.wait_for_url('**/products/add**', timeout=10000)
        expect(page.locator('#duplicate-warning')).to_be_visible()

        # Submitting without confirming writes nothing and says why.
        page.locator('#description').fill(duplicate)
        page.locator('button[type="submit"]').click()
        expect(page.locator('#duplicate-warning')).to_be_visible(timeout=10000)
        expect(page.locator('body')).to_contain_text('create a separate product')
        assert '/products/add' in page.url

        # Confirming creates it — and says plainly that the scanned identifier
        # stayed with the original, because a GTIN is globally unique.
        page.locator('#confirm_duplicate').check()
        page.locator('button[type="submit"]').click()
        expect(page.locator('body')).to_contain_text(duplicate, timeout=10000)
        expect(page.locator('.alert-danger')).to_contain_text(
            'already exists on product', timeout=10000)
