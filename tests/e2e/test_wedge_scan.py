"""
E2E Tests for Wedge Scan Capture (Story 4.1, FR35)

Covers the global #scan-input navbar field:
- it exists on every page (base.html carries it, no per-template work)
- a keyboard-wedge scan terminated by Enter posts the typed characters
  verbatim to POST /api/scan
- a successful scan clears the field and keeps focus
- a failed scan keeps the text, selects it, and toasts
- a blank Enter sends nothing
- a second Enter while a POST is in flight is ignored
- NFR9: the neighbouring metal-stock JA ID lookup is untouched

These tests mutate no data, so they are trivially safe under --reruns.
"""

import pytest
from playwright.sync_api import expect


SCAN_INPUT = '#scan-input'
JA_ID_INPUT = '#ja-id-lookup'


def simulate_wedge_scan(page, text):
    """Simulate a keyboard-wedge scanner: keystrokes then Enter.

    Modeled on tests/e2e/test_move_items.py's simulate_barcode_scan - a wedge
    is indistinguishable from fast typing, which is the whole point of FR35.
    """
    scan_input = page.locator(SCAN_INPUT)
    scan_input.fill('')
    scan_input.focus()
    scan_input.type(text)
    scan_input.press('Enter')


def record_scan_requests(page):
    """Install a route that records every POST /api/scan and lets it through.

    expect_response cannot assert the *absence* of a request, so the negative
    cases need a recorder instead.
    """
    calls = []

    def _handler(route, request):
        calls.append(request.post_data)
        route.continue_()

    page.route('**/api/scan', _handler)
    return calls


@pytest.mark.e2e
class TestScanFieldPresence:
    """FR35: 'the scan field captures a wedge scan on any page'."""

    # NOTE: explicit ids - a '/' in a generated test id becomes a directory
    # separator in tests/e2e/debug_utils.py's per-test output folder name.
    @pytest.mark.parametrize('path', [
        '/',                  # home
        '/inventory',         # metal-stock list
        '/products/add',      # catalog create form
        '/inventory/move',    # a page that already owns its own scan input
    ], ids=['home', 'inventory_list', 'product_add', 'inventory_move'])
    def test_scan_input_present_on_every_page(self, page, live_server, path):
        """The field comes from base.html, so no template was touched for it."""
        page.goto(f'{live_server.url}{path}')
        expect(page.locator(SCAN_INPUT)).to_be_visible(timeout=5000)

    def test_scan_field_is_not_a_search_input(self, page, live_server):
        """It must not match main.js's '/' focus-search selector
        (input[type=search], input[name*=search], #search)."""
        page.goto(f'{live_server.url}/inventory')
        scan_input = page.locator(SCAN_INPUT)
        expect(scan_input).to_have_attribute('type', 'text', timeout=5000)
        assert page.locator('#scan-input[name*="search"]').count() == 0
        assert page.locator('#scan-input[type="search"]').count() == 0

    def test_scan_capture_script_is_loaded(self, page, live_server):
        """scan-capture.js is a global <script>, like main.js."""
        page.goto(f'{live_server.url}/')
        assert page.evaluate('() => typeof window.ScanCapture') == 'object'


@pytest.mark.e2e
class TestWedgeScanCapture:
    """The capture loop itself (FR35)."""

    def test_scan_posts_raw_text_unmodified(self, page, live_server):
        """The scanned characters reach the server verbatim - no uppercasing,
        no normalization, no client-side classification."""
        page.goto(f'{live_server.url}/')

        with page.expect_response('**/api/scan') as response_info:
            simulate_wedge_scan(page, '96WITabc1234567')

        response = response_info.value
        assert response.status == 200
        assert response.request.post_data_json['raw'] == '96WITabc1234567'
        body = response.json()
        assert body['success'] is True
        assert body['raw'] == '96WITabc1234567'
        assert body['outcome'] == 'unrouted'

    @pytest.mark.parametrize('scanned', [
        '00012345678905',       # manufacturer GTIN-14
        '96WITABC1234567',      # internal GS1 AI-96 payload
        'mIxEd-CaSe_Text',      # case is significant and preserved
        'a b c',                # interior whitespace survives
    ])
    def test_various_payloads_post_verbatim(self, page, live_server, scanned):
        """The client classifies nothing; every payload posts the same way."""
        page.goto(f'{live_server.url}/inventory')

        with page.expect_response('**/api/scan') as response_info:
            simulate_wedge_scan(page, scanned)

        assert response_info.value.request.post_data_json['raw'] == scanned

    def test_successful_scan_clears_field_and_keeps_focus(self, page, live_server):
        """Consecutive scans need no mouse (FR35)."""
        page.goto(f'{live_server.url}/')

        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, '00012345678905')

        scan_input = page.locator(SCAN_INPUT)
        expect(scan_input).to_have_value('', timeout=5000)
        expect(scan_input).to_be_focused(timeout=5000)

    def test_two_consecutive_scans_each_post_once(self, page, live_server):
        """The field is ready for the next scan immediately."""
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, 'FIRST-SCAN')
        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, 'SECOND-SCAN')

        page.wait_for_timeout(500)
        assert len(calls) == 2

    def test_blank_enter_sends_no_request(self, page, live_server):
        """Nothing was scanned, so nothing is transmitted."""
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        scan_input = page.locator(SCAN_INPUT)
        scan_input.fill('')
        scan_input.focus()
        scan_input.press('Enter')
        page.wait_for_timeout(1000)

        assert calls == []

    def test_whitespace_only_enter_sends_no_request(self, page, live_server):
        """Same as blank: a stray Enter on a space is not a scan."""
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        scan_input = page.locator(SCAN_INPUT)
        scan_input.fill('')
        scan_input.focus()
        scan_input.type('   ')
        scan_input.press('Enter')
        page.wait_for_timeout(1000)

        assert calls == []

    def test_second_enter_while_in_flight_is_ignored_but_not_silently(
            self, page, live_server):
        """A fast double-scan must not produce two overlapping requests.

        Both keydowns are dispatched inside one synchronous JS task, so the
        second is guaranteed to arrive while the fetch promise is pending -
        which a timing-based double press could not guarantee.

        The dropped scan must be announced: a silently ignored Enter followed
        by the field clearing on the FIRST scan's response is indistinguishable
        from a captured scan, which is how a scan gets lost (FR35).
        """
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            el.value = 'DOUBLE-SCAN';
            const press = () => el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            press();
            press();
        }""")

        expect(page.locator('.toast.text-bg-warning')).to_be_visible(timeout=5000)
        page.wait_for_timeout(1500)

        assert len(calls) == 1


@pytest.mark.e2e
class TestScanFailureHandling:
    """A scan is never lost (FR35)."""

    def test_failed_scan_retains_and_selects_text_and_toasts(self, page, live_server):
        """Rejected by the server: the operator can retry or read it off."""
        page.goto(f'{live_server.url}/')
        page.route('**/api/scan', lambda route: route.fulfill(
            status=400,
            content_type='application/json',
            body='{"success": false, "error": {"code": "invalid_field",'
                 ' "message": "raw must be a string", "field": "raw"}}'))

        simulate_wedge_scan(page, 'LOST-SCAN-GUARD')

        scan_input = page.locator(SCAN_INPUT)
        expect(scan_input).to_have_value('LOST-SCAN-GUARD', timeout=5000)
        expect(scan_input).to_be_focused(timeout=5000)
        expect(page.locator('.toast.text-bg-danger')).to_be_visible(timeout=5000)

        selected = page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            return el.selectionStart === 0 && el.selectionEnd === el.value.length;
        }""")
        assert selected is True

    def test_network_failure_retains_text_and_toasts(self, page, live_server):
        """A rejected fetch is handled the same way as a non-2xx."""
        page.goto(f'{live_server.url}/')
        page.route('**/api/scan', lambda route: route.abort())

        simulate_wedge_scan(page, 'OFFLINE-SCAN')

        expect(page.locator(SCAN_INPUT)).to_have_value('OFFLINE-SCAN', timeout=5000)
        expect(page.locator('.toast.text-bg-danger')).to_be_visible(timeout=5000)

    def test_server_error_message_is_escaped_not_rendered(self, page, live_server):
        """`showToast` interpolates into innerHTML, so the server-supplied
        message must reach it escaped.

        A barcode label is attacker-suppliable physical input, and Stories
        4.2/4.3 will echo the scanned payload back inside these messages.
        """
        page.goto(f'{live_server.url}/')
        page.route('**/api/scan', lambda route: route.fulfill(
            status=400,
            content_type='application/json',
            body='{"success": false, "error": {"code": "invalid_field",'
                 ' "message": "<img src=x onerror=\\"window.__pwned=1\\">",'
                 ' "field": "raw"}}'))

        simulate_wedge_scan(page, 'XSS-PROBE')

        toast = page.locator('.toast.text-bg-danger')
        expect(toast).to_be_visible(timeout=5000)
        assert '<img' in toast.inner_text()              # shown as literal text
        assert page.locator('.toast img').count() == 0   # never parsed as markup
        assert page.evaluate('() => window.__pwned') is None


@pytest.mark.e2e
class TestLateResponseDoesNotClobberTheOperator:
    """The response is asynchronous; the operator is not idle while it flies.

    Both cases stub `window.fetch` with a deliberately slow promise so the
    in-flight window is deterministic rather than a race against the server.
    """

    SLOW_FETCH = """(delayMs) => {
        window.fetch = () => new Promise(resolve => setTimeout(
            () => resolve(new Response(
                JSON.stringify({success: true, raw: 'AAA', outcome: 'unrouted'}),
                {status: 200, headers: {'Content-Type': 'application/json'}})),
            delayMs));
    }"""

    def _press_enter(self, page, value):
        page.evaluate("""(value) => {
            const el = document.getElementById('scan-input');
            el.value = value;
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
        }""", value)

    def test_late_success_does_not_erase_newer_keystrokes(self, page, live_server):
        """Clearing the field unconditionally would wipe a scan in progress and
        still show the cleared-field 'accepted' signal - a lost scan (FR35)."""
        page.goto(f'{live_server.url}/')
        page.evaluate(self.SLOW_FETCH, 400)

        self._press_enter(page, 'AAA')
        page.evaluate("() => { document.getElementById('scan-input').value = 'AAABBB'; }")
        page.wait_for_timeout(1200)

        expect(page.locator(SCAN_INPUT)).to_have_value('AAABBB', timeout=5000)

    def test_late_response_does_not_steal_focus_from_another_field(
            self, page, live_server):
        """If the operator has moved on, a returning response must not yank
        focus back mid-typing."""
        page.goto(f'{live_server.url}/inventory')
        page.evaluate(self.SLOW_FETCH, 400)

        self._press_enter(page, 'AAA')
        page.locator(JA_ID_INPUT).focus()
        page.wait_for_timeout(1200)

        expect(page.locator(JA_ID_INPUT)).to_be_focused(timeout=5000)


@pytest.mark.e2e
class TestJaIdLookupRegression:
    """NFR9: metal-stock scanning is untouched by the new field."""

    def test_ja_id_lookup_still_navigates_and_issues_no_scan_request(
            self, page, live_server):
        """The JA ID field navigates client-side exactly as before, and the
        scan endpoint is never involved."""
        page.goto(f'{live_server.url}/inventory')
        calls = record_scan_requests(page)

        # Both navbar fields coexist
        expect(page.locator(JA_ID_INPUT)).to_be_visible(timeout=5000)
        expect(page.locator(SCAN_INPUT)).to_be_visible(timeout=5000)

        with page.expect_request('**/inventory/edit/JA000123'):
            lookup = page.locator(JA_ID_INPUT)
            lookup.fill('JA000123')
            lookup.press('Enter')

        page.wait_for_timeout(500)
        assert calls == []

    def test_ja_id_lookup_still_uppercases_input(self, page, live_server):
        """Its input handler is unchanged - and the scan field must NOT
        inherit that behavior."""
        page.goto(f'{live_server.url}/inventory')

        lookup = page.locator(JA_ID_INPUT)
        lookup.fill('ja000123')
        expect(lookup).to_have_value('JA000123', timeout=5000)

        scan_input = page.locator(SCAN_INPUT)
        scan_input.fill('ja000123')
        expect(scan_input).to_have_value('ja000123', timeout=5000)
