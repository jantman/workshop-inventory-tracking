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

import json

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
        '/no-such-page',      # the 404 page - errors/404.html extends base.html too
    ], ids=['home', 'inventory_list', 'product_add', 'inventory_move', 'error_404'])
    def test_scan_input_present_on_every_page(self, page, live_server, path):
        """The field comes from base.html, so no template was touched for it.

        The error page is included deliberately: it is a page an operator lands
        on without choosing to, and it is the one most easily missed by a
        route-driven check.
        """
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

    def test_scan_capture_script_is_loaded_and_bound(self, page, live_server):
        """scan-capture.js is a global <script>, like main.js.

        The export happens at parse time and is true even when `init()` bailed
        out at `if (!this.input) return;`, so assert the binding too — that is
        the property the field actually depends on.
        """
        page.goto(f'{live_server.url}/')
        assert page.evaluate('() => typeof window.ScanCapture') == 'object'
        assert page.evaluate(
            "() => window.ScanCapture.input === document.getElementById('scan-input')") is True


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
        """The field is ready for the next scan immediately.

        Asserts the payloads, not just the count: two requests both carrying
        FIRST-SCAN is precisely the residue bug a consecutive-scan test exists
        to catch, and a count-only assertion cannot see it.
        """
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, 'FIRST-SCAN')
        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, 'SECOND-SCAN')

        page.wait_for_timeout(500)
        assert [json.loads(c)['raw'] for c in calls] == ['FIRST-SCAN', 'SECOND-SCAN']

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

    def test_blank_gate_uses_the_servers_trim_set_not_js_trim(self, page, live_server):
        """The client's "is this blank" test must match `_SCAN_TRIM` exactly.

        JS `trim()` strips the full Unicode whitespace set, including \\x0b,
        \\x0c, NBSP and BOM - all of which the server deliberately KEEPS (see
        test_other_control_characters_are_also_never_trimmed). Gating on
        `trim()` would silently drop a payload the server would have accepted,
        with no request and no toast (FR35).
        """
        page.goto(f'{live_server.url}/')

        kept = page.evaluate("""() => ['\\x0b', '\\x0c', '\\u00a0', '\\ufeff', '\\x1e']
            .filter(c => window.ScanCapture.stripOuter(c) === c)""")
        assert kept == ['\x0b', '\x0c', '\u00a0', '\ufeff', '\x1e']

        trimmed = page.evaluate(
            "() => [' ', '\\t', '\\r', '\\n'].map(c => window.ScanCapture.stripOuter(c))")
        assert trimmed == ['', '', '', '']

    @pytest.mark.parametrize('typed', [
        '  0123  ',                 # plain outer spaces
        '\t STOCK \t',              # tabs and spaces, both in the trim set
        'a b\tc',                   # interior whitespace, kept by both sides
        '\u00a0NBSP\u00a0',       # NBSP: JS trim() strips it, both rules keep it
        '\ufeffBOM',               # BOM: likewise
        '\x0bVT\x0c',               # VT/FF: str.strip() strips them, both rules keep them
    ], ids=['spaces', 'tabs', 'interior', 'nbsp', 'bom', 'vt_ff'])
    def test_server_echo_matches_the_clients_own_trim_rule(
            self, page, live_server, typed):
        """The two implementations of the trim rule, compared end to end.

        `_SCAN_TRIM` and `ScanCapture.stripOuter` are separate copies of one
        rule, and the client never reads `data.raw` - so nothing else in the
        suite would notice them diverging; each side is only ever pinned
        against its own expectations. This drives the real field and compares
        the server's echo against the client's own function (FR35).
        """
        page.goto(f'{live_server.url}/')

        # Value set directly so control characters reach the field byte-exact;
        # the terminator below is still a real key press.
        page.evaluate("""(v) => {
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = v;
        }""", typed)

        with page.expect_response('**/api/scan') as response_info:
            page.locator(SCAN_INPUT).press('Enter')

        expected = page.evaluate('(v) => window.ScanCapture.stripOuter(v)', typed)
        assert response_info.value.json()['raw'] == expected

    def test_crlf_terminator_posts_once_and_is_not_called_a_dropped_scan(
            self, page, live_server):
        """ONE scan can send TWO Enter presses, and that is not a double-scan.

        HID has no separate LF key, so a wedge programmed with a CR+LF suffix
        emits Return twice in the same burst; the second always lands inside
        the first one's in-flight window. Treating it as a dropped scan would
        put a "rescan this item" warning on every single scan and invite the
        operator to double-process an item that was captured (FR35).

        The keys here are REAL browser input - only `fetch` is stubbed, to make
        the in-flight window deterministic rather than a race against the
        server.
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__posts = [];
            window.fetch = (url, opts) => {
                window.__posts.push(JSON.parse(opts.body).raw);
                return new Promise(resolve => setTimeout(() => resolve(new Response(
                    JSON.stringify({success: true, raw: 'CRLF-SCAN', outcome: 'unrouted'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}})), 400));
            };
        }""")

        scan_input = page.locator(SCAN_INPUT)
        scan_input.focus()
        scan_input.type('CRLF-SCAN')
        scan_input.press('Enter')            # CR
        scan_input.press('Enter')            # LF, same burst, field unchanged
        page.wait_for_timeout(1200)

        assert page.evaluate('() => window.__posts') == ['CRLF-SCAN']
        assert page.locator('.toast.text-bg-warning').count() == 0
        expect(scan_input).to_have_value('', timeout=5000)

    def test_second_burst_while_in_flight_is_dropped_but_not_silently(
            self, page, live_server):
        """A second burst - one that GREW the field - is a genuine second scan.

        Both keydowns are dispatched inside one synchronous JS task, so the
        second is guaranteed to arrive while the fetch promise is pending.

        Unlike the duplicate terminator above, this scan really is dropped, and
        a silent drop followed by the field clearing on the FIRST scan's
        response is indistinguishable from a captured scan (FR35).
        """
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'SCAN-ONE';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            el.value = 'SCAN-ONESCAN-TWO';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
        }""")

        expect(page.locator('.toast.text-bg-warning')).to_be_visible(timeout=5000)
        page.wait_for_timeout(1500)

        assert [json.loads(c)['raw'] for c in calls] == ['SCAN-ONE']

    def test_bare_enter_on_merged_residue_is_refused_not_posted(
            self, page, live_server):
        """Selecting the residue only closes the path where the next burst TYPES.

        A bare Enter - the obvious response to "rescan this item", and what a
        repeat-trigger scanner emits - would otherwise POST 'SCAN1SCAN2' as one
        valid 200 scan. A silently WRONG scan is worse than the lost scan the
        in-flight guard exists to prevent (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__posts = [];
            window.__resolve = null;
            window.fetch = (url, opts) => {
                window.__posts.push(JSON.parse(opts.body).raw);
                return new Promise(r => { window.__resolve = r; });
            };
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'SCAN1';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            el.value = 'SCAN1SCAN2';         // second burst types in
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            window.__resolve(new Response(
                JSON.stringify({success: true, raw: 'SCAN1', outcome: 'unrouted'}),
                {status: 200, headers: {'Content-Type': 'application/json'}}));
        }""")

        expect(page.locator('.toast.text-bg-warning')).to_be_visible(timeout=5000)
        page.wait_for_timeout(300)

        # The operator does the obvious thing with the retained text.
        page.locator(SCAN_INPUT).press('Enter')
        page.wait_for_timeout(500)

        assert page.evaluate('() => window.__posts') == ['SCAN1']   # never SCAN1SCAN2
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        expect(page.locator('.toast.text-bg-danger')).to_be_visible(timeout=5000)

    def test_ime_composition_enter_does_not_submit(self, page, live_server):
        """An IME commit fires Enter too; it ends a composition, not a scan.

        Acting on it would post a partial string (FR35).
        """
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'PARTIAL';
            el.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', isComposing: true, bubbles: true, cancelable: true}));
        }""")
        page.wait_for_timeout(800)

        assert calls == []
        expect(page.locator(SCAN_INPUT)).to_have_value('PARTIAL', timeout=5000)

    def test_typed_ahead_burst_does_not_concatenate_onto_the_next_scan(
            self, page, live_server):
        """The dropped burst's CHARACTERS, not just its Enter, must not survive.

        A real wedge types before it sends Enter, so a double-scan leaves the
        field holding 'SCAN1SCAN2'. If that residue is left un-selected, the
        operator's rescan appends again and POSTs the concatenation as one
        valid scan - a silently WRONG scan, which is worse than a lost one
        (FR35).
        """
        page.goto(f'{live_server.url}/')
        calls = record_scan_requests(page)

        # Simulate the wedge faithfully: first burst + Enter, then the second
        # burst's characters land while the first POST is still in flight.
        page.evaluate("""() => {
            window.__slowResolve = null;
            // Keep the original: `fetch` is an OWN property of window in
            // Chromium, so `delete window.fetch` removes it outright.
            window.__realFetch = window.fetch;
            window.fetch = () => new Promise(r => { window.__slowResolve = r; });
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'SCAN1';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            el.value = 'SCAN1SCAN2';            // second burst types in
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
        }""")

        expect(page.locator('.toast.text-bg-warning')).to_be_visible(timeout=5000)

        # The residue is selected, so the next keystroke replaces it.
        selected = page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            return el.selectionStart === 0 && el.selectionEnd === el.value.length;
        }""")
        assert selected is True

        # Let the first POST land, then scan again for real.
        page.evaluate("""() => {
            window.__slowResolve(new Response(
                JSON.stringify({success: true, raw: 'SCAN1', outcome: 'unrouted'}),
                {status: 200, headers: {'Content-Type': 'application/json'}}));
            window.fetch = window.__realFetch;
        }""")
        page.wait_for_timeout(300)

        with page.expect_response('**/api/scan'):
            page.locator(SCAN_INPUT).type('SCAN3')
            page.locator(SCAN_INPUT).press('Enter')

        assert [json.loads(c)['raw'] for c in calls] == ['SCAN3']


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

    def test_unrestorable_scan_text_is_surfaced_in_the_toast(self, page, live_server):
        """When the field already holds a fresh scan, the failed text cannot be
        restored into it - so it must appear somewhere.

        Otherwise it exists nowhere on either side while the toast still tells
        the operator the scan was kept: a lost scan wearing a kept-scan label
        (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__slowReject = null;
            window.fetch = () => new Promise((_, rej) => { window.__slowReject = rej; });
        }""")

        page.evaluate("""() => {
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'FAILED-SCAN';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            el.value = 'A-FRESH-SCAN';          // operator has moved on
            window.__slowReject(new TypeError('network'));
        }""")

        toast = page.locator('.toast.text-bg-danger')
        expect(toast).to_be_visible(timeout=5000)
        assert 'FAILED-SCAN' in toast.inner_text()
        # The fresh scan is not overwritten by the failed one.
        expect(page.locator(SCAN_INPUT)).to_have_value('A-FRESH-SCAN', timeout=5000)

    def test_timeout_is_not_reported_as_an_unreachable_server(self, page, live_server):
        """An abort means the outcome is UNKNOWN - the server may have taken
        the scan. Telling the operator it was unreachable invites a rescan of
        something already accepted, which matters once Stories 4.3/4.5 give
        this endpoint side effects.
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.ScanCapture.config.timeoutMs = 200;
            // Honour the abort signal the way a real fetch does.
            window.fetch = (url, opts) => new Promise((_, reject) => {
                opts.signal.addEventListener('abort', () => {
                    const e = new Error('aborted');
                    e.name = 'AbortError';
                    reject(e);
                });
            });
        }""")

        simulate_wedge_scan(page, 'TIMED-OUT-SCAN')

        toast = page.locator('.toast.text-bg-danger')
        expect(toast).to_be_visible(timeout=5000)
        assert 'timed out' in toast.inner_text().lower()
        assert 'could not reach' not in toast.inner_text().lower()
        expect(page.locator(SCAN_INPUT)).to_have_value('TIMED-OUT-SCAN', timeout=5000)

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

    def test_late_failure_does_not_steal_focus_from_another_field(
            self, page, live_server):
        """The FAILURE path must respect the same guard as the success path.

        `select()` focuses the element as a side effect, so calling it outside
        the refocus guard would yank focus back from the JA ID field the
        operator moved to - the very defect refocus() exists to prevent, just
        via a different call.
        """
        page.goto(f'{live_server.url}/inventory')
        page.evaluate("""(delayMs) => {
            window.fetch = () => new Promise(resolve => setTimeout(
                () => resolve(new Response(
                    JSON.stringify({success: false, error: {code: 'invalid_field',
                        message: 'nope', field: 'raw'}}),
                    {status: 400, headers: {'Content-Type': 'application/json'}})),
                delayMs));
        }""", 400)

        self._press_enter(page, 'AAA')
        page.locator(JA_ID_INPUT).focus()
        page.wait_for_timeout(1200)

        expect(page.locator(JA_ID_INPUT)).to_be_focused(timeout=5000)
        expect(page.locator('.toast.text-bg-danger')).to_be_visible(timeout=5000)


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
