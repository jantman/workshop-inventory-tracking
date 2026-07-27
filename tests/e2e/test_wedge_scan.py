"""
E2E Tests for Wedge Scan Capture (Story 4.1, FR35; Story 4.5, FR36)

Covers the global #scan-input navbar field:
- it exists on every page (base.html carries it, no per-template work)
- a keyboard-wedge scan terminated by Enter posts the typed characters
  verbatim to POST /api/scan
- a successful scan clears the field and FOLLOWS the destination the server
  chose (Story 4.5 — before it, a success left the operator in place)
- a failed scan keeps the text, selects it, and toasts
- a blank Enter sends nothing
- a second Enter while a POST is in flight is ignored
- NFR9: the neighbouring metal-stock JA ID lookup is untouched

Where these tests land is tests/e2e/test_scan_routing.py's subject; this file
is still about the CAPTURE loop, so the stubbed cases below route to a
same-document fragment. That runs the one new client line (`window.location
.href = data.url`) without tearing the page down, which is what lets a test
about the field's state still be able to inspect it afterwards.

These tests mutate no data, so they are trivially safe under --reruns.
"""

import json

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import SCAN_INPUT, simulate_wedge_scan, unstored_gtin


JA_ID_INPUT = '#ja-id-lookup'

# A same-document destination: setting location.href to the CURRENT path with a
# different fragment does not reload the page, so a stubbed success can exercise
# the navigation line and still leave window.__posts, the toasts and the field
# state readable. Root-relative rather than a bare fragment because the client
# follows only same-origin, root-relative paths — every test using this opens
# `/`, so this is that page plus a fragment.
FRAGMENT_URL = '/#scan-landing'


def routed_body(raw, url=FRAGMENT_URL, kind='free_text', outcome='create',
                hit_count=0):
    """The six-key envelope POST /api/scan answers with since Story 4.5.

    Built here rather than written out per stub so a stubbed success cannot
    quietly keep answering in Story 4.1's retired three-key shape.
    """
    return json.dumps({'success': True, 'raw': raw, 'kind': kind,
                       'outcome': outcome, 'url': url, 'hit_count': hit_count})


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


def record_scan_responses(page, rewrite_url=None):
    """Record the REAL server's scan envelopes, optionally re-aiming the URL.

    Two problems this solves at once, both created by Story 4.5's navigation:

    1. `Response.json()` reads the body out of the browser, and a success now
       navigates immediately — so reading the envelope after the fact races the
       page teardown. Fetching it here keeps it Python-side, where nothing can
       evict it.
    2. A test about the CAPTURE loop still needs the page it was inspecting.
       Passing `rewrite_url` swaps the server's destination for a same-document
       fragment, so the navigation line still runs and the page survives.

    The envelope recorded is always the server's own, unmodified.
    """
    bodies = []

    def _handler(route, request):
        response = route.fetch()
        body = response.json()
        bodies.append(body)
        served = dict(body)
        if rewrite_url is not None and served.get('url'):
            served['url'] = rewrite_url
        route.fulfill(status=response.status, body=json.dumps(served),
                      headers={'Content-Type': 'application/json'})

    page.route('**/api/scan', _handler)
    return bodies


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
        bodies = record_scan_responses(page, rewrite_url=FRAGMENT_URL)

        with page.expect_response('**/api/scan') as response_info:
            simulate_wedge_scan(page, '96WITabc1234567')

        assert response_info.value.request.post_data_json['raw'] == '96WITabc1234567'
        page.wait_for_timeout(500)
        assert len(bodies) == 1
        body = bodies[0]
        assert body['success'] is True
        assert body['raw'] == '96WITabc1234567'
        # Story 4.5 retires 'unrouted': every scan answers with one of three
        # outcomes and a non-empty in-app URL (FR36).
        assert body['outcome'] in {'product', 'search', 'create'}
        assert body['url'].startswith('/')

    @pytest.mark.parametrize('scanned', [
        '00012345678905',       # manufacturer GTIN-14
        '96WITABC1234567',      # internal GS1 AI-96 payload
        'mIxEd-CaSe_Text',      # case is significant and preserved
        'a b c',                # interior whitespace survives
    ])
    def test_various_payloads_post_verbatim(self, page, live_server, scanned):
        """The client classifies nothing; every payload posts the same way."""
        page.goto(f'{live_server.url}/inventory')
        record_scan_responses(page, rewrite_url=FRAGMENT_URL)

        with page.expect_response('**/api/scan') as response_info:
            simulate_wedge_scan(page, scanned)

        assert response_info.value.request.post_data_json['raw'] == scanned

    def test_successful_scan_clears_the_field_and_follows_the_routed_url(
            self, page, live_server):
        """Story 4.5 replaces 4.1's "clears the field and keeps focus".

        A successful scan is now a LANDING, not a no-op: the server answers with
        a destination and the client follows it (FR36/FR40). The field is still
        cleared first — that is the accepted signal — but the operator does not
        stay put, so "keeps focus" is no longer the property to assert.
        """
        page.goto(f'{live_server.url}/')
        bodies = record_scan_responses(page)        # real destination, no rewrite
        gtin = unstored_gtin(live_server)

        with page.expect_response('**/api/scan'):
            simulate_wedge_scan(page, gtin)

        page.wait_for_url('**/products/add**', timeout=10000)
        assert bodies[0]['outcome'] == 'create'     # matched nothing anywhere
        assert bodies[0]['url'].startswith('/products/add')

        # ...and the create form opened with the scanned identifier, editable.
        expect(page.locator('#identifier_value')).to_have_value(
            f'0{gtin}', timeout=5000)

    def test_the_client_follows_the_url_verbatim_without_reading_kind(
            self, page, live_server):
        """AD-5: the client reads `data.url` and follows it. It must not branch
        on `kind` or `outcome` to choose a destination — if it did, FR36's
        precedence would exist in two languages.

        The stub therefore answers with a destination that contradicts its own
        `kind`/`outcome`, and the client must still go where `url` says.
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""(body) => {
            window.fetch = () => Promise.resolve(new Response(
                body, {status: 200, headers: {'Content-Type': 'application/json'}}));
        }""", routed_body('ANY', url='/products/tags', kind='gtin',
                          outcome='product', hit_count=7))

        simulate_wedge_scan(page, 'ANY')

        page.wait_for_url('**/products/tags', timeout=10000)

    def test_two_consecutive_scans_each_post_once(self, page, live_server):
        """The field is ready for the next scan immediately.

        Asserts the payloads, not just the count: two requests both carrying
        FIRST-SCAN is precisely the residue bug a consecutive-scan test exists
        to catch, and a count-only assertion cannot see it.

        `fetch` is stubbed with a fragment destination so that the routed
        navigation really runs while the page — and therefore the record of what
        was posted — survives to be inspected.
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__posts = [];
            window.fetch = (url, opts) => {
                const raw = JSON.parse(opts.body).raw;
                window.__posts.push(raw);
                return Promise.resolve(new Response(
                    JSON.stringify({success: true, raw: raw, kind: 'free_text',
                                    outcome: 'create', url: '/#scan-landing',
                                    hit_count: 0}),
                    {status: 200, headers: {'Content-Type': 'application/json'}}));
            };
        }""")

        simulate_wedge_scan(page, 'FIRST-SCAN')
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        simulate_wedge_scan(page, 'SECOND-SCAN')
        page.wait_for_timeout(500)

        assert page.evaluate('() => window.__posts') == ['FIRST-SCAN', 'SECOND-SCAN']
        assert page.url.endswith(FRAGMENT_URL)      # the routed URL was followed

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
        bodies = record_scan_responses(page, rewrite_url=FRAGMENT_URL)

        # Value set directly so control characters reach the field byte-exact;
        # the terminator below is still a real key press.
        page.evaluate("""(v) => {
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = v;
        }""", typed)

        # Asked BEFORE the scan: an accepted scan navigates now (Story 4.5), and
        # a question put to a page that is unloading answers nothing.
        expected = page.evaluate('(v) => window.ScanCapture.stripOuter(v)', typed)

        with page.expect_response('**/api/scan'):
            page.locator(SCAN_INPUT).press('Enter')

        page.wait_for_timeout(500)
        assert bodies[0]['raw'] == expected

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
                    JSON.stringify({success: true, raw: 'CRLF-SCAN', kind: 'free_text',
                                    outcome: 'create', url: '/#scan-landing',
                                    hit_count: 0}),
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

        # `.first`: the accepted first scan raises a second warning of its own
        # once its response lands, because the field it cannot clear is merged.
        expect(page.locator('.toast.text-bg-warning').first).to_be_visible(timeout=5000)
        page.wait_for_timeout(1500)

        assert [json.loads(c)['raw'] for c in calls] == ['SCAN-ONE']

    def test_one_dropped_burst_warns_once_even_with_a_crlf_suffix(
            self, page, live_server):
        """A CR+LF wedge sends two Returns per burst, including the burst that
        gets dropped.

        Comparing only against the text in flight takes the "field has GROWN"
        branch twice, so one dropped item produced two identical "rescan this
        item" toasts - noise on the exact path that has to be trusted (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.fetch = () => new Promise(() => {});   // never settles
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'BURST-ONE';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));  // CR
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));  // LF
            el.value = 'BURST-ONEBURST-TWO';       // second burst, dropped
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));  // CR
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));  // LF
        }""")

        expect(page.locator('.toast.text-bg-warning')).to_be_visible(timeout=5000)
        page.wait_for_timeout(600)
        assert page.locator('.toast.text-bg-warning').count() == 1

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
                JSON.stringify({success: true, raw: 'SCAN1', kind: 'free_text',
                                outcome: 'create', url: '/#scan-landing',
                                hit_count: 0}),
                {status: 200, headers: {'Content-Type': 'application/json'}}));
        }""")

        expect(page.locator('.toast.text-bg-warning').first).to_be_visible(timeout=5000)
        page.wait_for_timeout(300)

        # The operator does the obvious thing with the retained text.
        page.locator(SCAN_INPUT).press('Enter')
        page.wait_for_timeout(500)

        assert page.evaluate('() => window.__posts') == ['SCAN1']   # never SCAN1SCAN2
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        danger = page.locator('.toast.text-bg-danger')
        expect(danger).to_be_visible(timeout=5000)
        # Refusing the text also erases it, so - like the unrestorable failed
        # scan - it has to exist somewhere the operator can still read.
        assert 'two scans run together' in danger.inner_text()
        assert 'SCAN1SCAN2' in danger.inner_text()

    def test_accepted_scan_says_so_when_the_field_cannot_be_cleared(
            self, page, live_server):
        """A cleared field is the only success signal, so the branch that cannot
        clear it must speak.

        Silence there is indistinguishable from a scan that never fired - the
        same reason the failure toast is mandatory - and the refusal the
        operator's next Enter earns talks about the field, not about the item
        already captured. Believing it was not captured is what produces the
        double-scan once Stories 4.3/4.5 add side effects (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__resolve = null;
            window.fetch = () => new Promise(r => { window.__resolve = r; });
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'ACCEPTED';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            // Typed ahead, no second Enter - so the in-flight guard never runs
            // and this branch is the only thing that can say anything.
            el.value = 'ACCEPTEDNEXT';
            window.__resolve(new Response(
                JSON.stringify({success: true, raw: 'ACCEPTED', kind: 'free_text',
                                outcome: 'create', url: '/#scan-landing',
                                hit_count: 0}),
                {status: 200, headers: {'Content-Type': 'application/json'}}));
        }""")

        toast = page.locator('.toast.text-bg-warning')
        expect(toast).to_be_visible(timeout=5000)
        assert 'accepted' in toast.inner_text().lower()
        # The typed-ahead characters are not erased by the confirmation.
        expect(page.locator(SCAN_INPUT)).to_have_value('ACCEPTEDNEXT', timeout=5000)

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
                JSON.stringify({success: true, raw: 'SCAN1', kind: 'free_text',
                                outcome: 'create', url: '/#scan-landing',
                                hit_count: 0}),
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
        toast = page.locator('.toast.text-bg-danger')
        expect(toast).to_be_visible(timeout=5000)
        # The message, not just the colour: showing the merged-residue refusal
        # here (or any unrelated danger toast the page raised) would otherwise
        # satisfy this assertion.
        assert 'raw must be a string' in toast.inner_text()

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
        toast = page.locator('.toast.text-bg-danger')
        expect(toast).to_be_visible(timeout=5000)
        assert 'could not reach the server' in toast.inner_text()

    def test_restored_text_does_not_concatenate_onto_the_next_burst(
            self, page, live_server):
        """The selection is the ONLY thing keeping a failed scan's restored text
        from merging with the next burst, and a click destroys it.

        The retry text is the value the operator is most likely to be looking
        at, so this is the likeliest route to the silently WRONG scan the
        residue machinery exists to refuse - and the one path that machinery did
        not cover, because the restore explicitly cleared the flag (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__posts = [];
            window.fetch = (url, opts) => {
                window.__posts.push(JSON.parse(opts.body).raw);
                return Promise.resolve(new Response(
                    JSON.stringify({success: false, error: {code: 'invalid_field',
                        message: 'nope', field: 'raw'}}),
                    {status: 400, headers: {'Content-Type': 'application/json'}}));
            };
        }""")

        simulate_wedge_scan(page, 'FAILED-ONE')
        expect(page.locator(SCAN_INPUT)).to_have_value('FAILED-ONE', timeout=5000)

        # The operator glances at another field and comes back: the selection is
        # gone, so the next burst APPENDS rather than replacing.
        page.locator(JA_ID_INPUT).click()
        page.locator(SCAN_INPUT).click()
        page.locator(SCAN_INPUT).press('End')
        page.locator(SCAN_INPUT).type('SCAN-TWO')
        page.locator(SCAN_INPUT).press('Enter')
        page.wait_for_timeout(600)

        assert page.evaluate('() => window.__posts') == ['FAILED-ONE']
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        assert 'two scans run together' in page.locator(
            '.toast.text-bg-danger').last.inner_text()

    def test_failure_landing_mid_burst_refuses_the_concatenation(
            self, page, live_server):
        """A wedge types its characters BEFORE its Enter, so a failure can land
        in the gap between them.

        On that branch the failed text is not restored - it goes into the toast -
        and nothing else marked the field, so the Enter the burst is about to
        send would POST 'FIRSTSECOND' as one valid scan (FR35).
        """
        page.goto(f'{live_server.url}/')
        page.evaluate("""() => {
            window.__posts = [];
            window.__reject = null;
            window.fetch = (url, opts) => {
                window.__posts.push(JSON.parse(opts.body).raw);
                return new Promise((_, rej) => { window.__reject = rej; });
            };
            const el = document.getElementById('scan-input');
            el.focus();
            el.value = 'FIRST';
            el.dispatchEvent(new KeyboardEvent(
                'keydown', {key: 'Enter', bubbles: true, cancelable: true}));
            el.value = 'FIRSTSECOND';      // second burst's characters, no Enter yet
            window.__reject(new TypeError('network'));
        }""")
        page.wait_for_timeout(300)

        # Now the second burst sends its terminator.
        page.locator(SCAN_INPUT).press('Enter')
        page.wait_for_timeout(500)

        assert page.evaluate('() => window.__posts') == ['FIRST']
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        assert 'two scans run together' in page.locator(
            '.toast.text-bg-danger').last.inner_text()

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
        """The server-supplied message must reach the operator as text.

        A barcode label is attacker-suppliable physical input, and Stories
        4.2/4.3 echo the scanned payload back inside these messages.

        `showToast` now builds the toast from DOM nodes and sets the message
        with `textContent`, so callers pass PLAIN TEXT and must not pre-escape
        (DW-54; `ScanCapture.notify` used to, while the sink interpolated into
        innerHTML). That makes the `'<img' in inner_text()` assertion below a
        double-escape detector as well as an injection one: escape twice and
        the operator gets `&lt;img`, and this goes red.
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

    The stub answers with a real routed destination since Story 4.5, which is
    what makes these two cases sharper than they were: navigation is a stronger
    form of the clobbering they guard against, and a page that reloads takes the
    operator's other field with it.
    """

    SLOW_FETCH = """(delayMs) => {
        window.fetch = () => new Promise(resolve => setTimeout(
            () => resolve(new Response(
                JSON.stringify({success: true, raw: 'AAA', kind: 'free_text',
                              outcome: 'create', url: '/products/add',
                              hit_count: 0}),
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
        # ...and the routed URL is not followed either: the response no longer
        # belongs to what is in the field, so it decides nothing about where the
        # operator goes.
        assert '/products/add' not in page.url

    def test_late_response_does_not_steal_focus_from_another_field(
            self, page, live_server):
        """If the operator has moved on, a returning response must not yank
        focus back mid-typing - nor navigate the page out from under them.

        Navigating is the same defect through a different call: `refocus()`
        already refuses to take focus back from another field, so Story 4.5's
        one new line follows `data.url` only when that refusal did not fire.

        Refusing to navigate must not be SILENT, though. The field cleared while
        the operator was looking elsewhere and the destination was dropped, so
        the scan gets a toast naming what was taken and saying it was not
        followed — the same reasoning as the contaminated-field branch, where
        silence reads as "never fired" and invites a rescan of something the
        server already has.
        """
        page.goto(f'{live_server.url}/inventory')
        page.evaluate(self.SLOW_FETCH, 400)

        self._press_enter(page, 'AAA')
        page.locator(JA_ID_INPUT).focus()
        page.wait_for_timeout(1200)

        expect(page.locator(JA_ID_INPUT)).to_be_focused(timeout=5000)
        assert '/products/add' not in page.url
        # The scan WAS accepted, and the cleared field says so.
        expect(page.locator(SCAN_INPUT)).to_have_value('', timeout=5000)
        # ...and so does the toast, which names the scan and its fate.
        toast = page.locator('.toast.text-bg-warning')
        expect(toast).to_be_visible(timeout=5000)
        assert 'accepted' in toast.inner_text().lower()
        assert 'AAA' in toast.inner_text()
        assert 'not followed' in toast.inner_text().lower()
        # Notifying still must not take focus back.
        expect(page.locator(JA_ID_INPUT)).to_be_focused()

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
