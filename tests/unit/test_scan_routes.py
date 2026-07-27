"""
Route tests for the wedge-scan endpoint, POST /api/scan (Stories 4.1 and 4.5).

Story 4.1 built the transport (FR35): the payload rules, the one narrow
whitespace rule, the AD-13 error envelope and the logging. Story 4.5 makes the
same endpoint the ROUTER (FR36/FR39/FR40/FR41): it resolves the cleaned scan
through `CatalogService.resolve_scan()` and answers with the destination, so the
endpoint now constructs a service and reads the database.

Three Story 4.1 assertions are deliberately retired here, and they are the only
pre-existing ones this story changes: `outcome == 'unrouted'`, "the endpoint
constructs no catalog service", and the three-key response shape. Each was
written to turn red exactly now.

Uses the `client` fixture, with real products created through `CatalogService`
against the shared `test_storage` — no mocking of the service or the ORM. The
two exceptions are labelled where they appear: the CSRF test builds a second app
with protection genuinely enabled, and the 500-path test needs a `resolve_scan`
that raises, which no input can produce.
"""

import logging
import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import pytest

from app.mariadb_catalog_service import CatalogService
from app.main.routes import (MAX_SCAN_LENGTH, _SCAN_LOG_CHARS,
                             _clean_scan_input, _scan_search_text,
                             _scan_url_value)
from app.models import IdentifierType, ScanKind
from app.utils import scan_router
from config import Config


# --- Vectors -----------------------------------------------------------------

# Trade item numbers, each with the canonical 14-digit key normalize_gtin folds
# every encoding of it onto. Shared with tests/unit/test_scan_resolution.py.
GTIN13 = '9506000134352'
GTIN13_KEY = '09506000134352'
UPCA = '012345678905'
UPCA_KEY = '00012345678905'
# Check-digit-valid and stored nowhere, in any test below.
GTIN_UNSTORED = '4006381333931'
GTIN_UNSTORED_KEY = '04006381333931'

# A manufacturer part number carrying a character the Crockford base-32
# internal-id alphabet does not, so a generated internal_id can never
# substring-match it and the hit lists here are deterministic.
MPN = 'RC0805-10K'
CUSTOMER_MPN = '296-1234-ND'


def _envelope(*records):
    """An ISO/IEC 15434 format-06 message carrying `records` verbatim."""
    return '[)>\x1e06' + ''.join(f'\x1d{record}' for record in records) + '\x1d\x1e\x04'


def _internal_scan(internal_id):
    """The bare element string an internal label carries: `<ai><token><id>`.

    Assembled from the CONFIGURED grammar (AD-16), never from a literal, so
    reconfiguring the pair does not turn these tests red.
    """
    return f'{Config.GS1_INTERNAL_AI}{Config.GS1_INTERNAL_TOKEN}{internal_id}'


def _query(url):
    """The query string of a routed URL, as a plain single-value dict.

    Asserted on rather than the raw URL text: parameter ORDER is werkzeug's
    business, and pinning it would make these tests fail for a reason that has
    nothing to do with routing.
    """
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def _path(url):
    return urlparse(url).path


def _create_link(html):
    """The href of the scan banner's "create a separate product instead" link.

    Read off the rendered page rather than rebuilt, so what is asserted is what
    the operator would actually click.
    """
    match = re.search(r'href="([^"]+)"[^>]*id="scan-banner-create"', html)
    assert match, 'the scan banner did not render a create link'
    return unescape(match.group(1))


@pytest.mark.unit
class TestCleanScanInput:
    """The one narrow whitespace rule, isolated from the transport."""

    @pytest.mark.parametrize('value, expected', [
        ('  0123 \r\n', '0123'),                     # every trimmed character at once
        (' 0123', '0123'),                           # leading space
        ('0123 ', '0123'),                           # trailing space
        ('\t0123\t', '0123'),                        # tabs
        ('\r\n0123\r\n', '0123'),                    # CR/LF a wedge may append
        ('a b\tc', 'a b\tc'),                        # interior whitespace kept
        ('96WITabc', '96WITabc'),                    # case never folded
        ('', ''),                                    # empty stays empty
        ('   ', ''),                                 # whitespace-only collapses to blank
    ])
    def test_trims_only_space_tab_cr_lf(self, value, expected):
        """FR35: leading/trailing space, tab, CR and LF only."""
        assert _clean_scan_input(value) == expected

    @pytest.mark.parametrize('value', [
        '\x1dP123',                                  # leading GS
        '[)>\x1e06\x1dP123\x1e\x04',                 # full ISO/IEC 15434 format-06 envelope
        '\x1e06\x1d',                                # bare RS/GS pair
        '\x04',                                      # trailing EOT alone
        '\x1c\x1f',                                  # FS/US - str.strip() would eat these
    ])
    def test_iso15434_control_characters_are_never_trimmed(self, value):
        """A bare str.strip() eats \\x1c-\\x1f; Story 4.4's parser needs them."""
        assert _clean_scan_input(value) == value

    @pytest.mark.parametrize('char', [
        '\x0b',                                      # VT - a programmable wedge suffix
        '\x0c',                                      # FF - likewise
        '\x00',                                      # NUL
    ], ids=['vertical_tab', 'form_feed', 'nul'])
    def test_other_control_characters_are_also_never_trimmed(self, char):
        """Pins the exact boundary of `_SCAN_TRIM`.

        FR35 names space, tab, CR and LF and nothing else, so these survive
        even though `str.strip()` would remove \\x0b and \\x0c. If a scanner is
        ever programmed with one of these as a suffix, Story 4.4 sees it in the
        payload — that is a deliberate consequence of the narrow rule, not an
        oversight, and this test exists so changing it is a conscious act.
        """
        assert _clean_scan_input(f'{char}P123{char}') == f'{char}P123{char}'

    def test_bare_strip_would_have_destroyed_the_envelope(self):
        """Guards the reason `_SCAN_TRIM` is explicit rather than defaulted.

        Python classifies \\x1c-\\x1f as whitespace, so `str.strip()` with no
        argument eats the record separator that terminates an ISO/IEC 15434
        record — Story 4.4 would then parse a truncated envelope.
        """
        envelope = '[)>\x1e06\x1dP123\x1e'
        assert envelope.strip() == '[)>\x1e06\x1dP123'   # this is what NOT to do
        assert _clean_scan_input(envelope) == envelope   # RS survives


@pytest.mark.unit
class TestScanCaptureEndpoint:
    """Every server row of the Story 4.1 I/O & Edge-Case matrix (FR35)."""

    def test_happy_path_echoes_raw_and_routes_it(self, client):
        """A plain GTIN posts, comes back verbatim, and carries a destination.

        Replaces Story 4.1's `test_happy_path_echoes_raw_unrouted`: `'unrouted'`
        is retired, and every scan now answers with one of three outcomes and a
        non-empty in-app URL (FR36).
        """
        resp = client.post('/api/scan', json={'raw': UPCA_KEY})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['raw'] == UPCA_KEY
        assert data['kind'] == ScanKind.GTIN.value
        assert data['outcome'] in {'product', 'search', 'create'}
        assert data['url'].startswith('/')

    @pytest.mark.parametrize('raw, expected', [
        ('  0123 \r\n', '0123'),                     # outer whitespace stripped
        ('[)>\x1e06\x1dP123\x1e\x04', '[)>\x1e06\x1dP123\x1e\x04'),  # control chars survive
        ('a b\tc', 'a b\tc'),                        # interior whitespace kept
        ('96WITabc', '96WITabc'),                    # case preserved, never uppercased
        ('96WITABC1234567', '96WITABC1234567'),      # internal GS1 AI-96 payload
        ('  [)>\x1e06\x1dP123\x1e\x04  ', '[)>\x1e06\x1dP123\x1e\x04'),  # trim outside, keep inside
    ])
    def test_raw_is_echoed_byte_for_byte(self, client, raw, expected):
        """FR35: verbatim apart from outer space/tab/CR/LF.

        The echo is what this test is about; the outcome is asserted only to be
        one of the three, because every one of these payloads routes somewhere
        and none may dead-end (FR36).
        """
        resp = client.post('/api/scan', json={'raw': raw})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['raw'] == expected
        assert data['outcome'] in {'product', 'search', 'create'}
        assert data['url']

    def test_no_unicode_normalization(self, client):
        """Composed vs decomposed forms stay distinct payloads, never folded."""
        composed = '\u00dcber'                   # U+00DC LATIN CAPITAL U WITH DIAERESIS
        decomposed = 'U\u0308ber'                # U + COMBINING DIAERESIS - NFC merges these
        assert composed != decomposed
        assert client.post('/api/scan', json={'raw': composed}).get_json()['raw'] == composed
        assert client.post('/api/scan', json={'raw': decomposed}).get_json()['raw'] == decomposed

    def test_missing_raw_is_invalid_field(self, client):
        """AD-13 object envelope naming the offending field."""
        resp = client.post('/api/scan', json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert isinstance(data['error'], dict)       # object envelope, NOT a bare string
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'

    @pytest.mark.parametrize('raw', [
        '',                                          # empty string
        '   ',                                       # spaces only
        '\t\r\n',                                    # the other trimmed characters
        ' \t ',                                      # mixture
    ])
    def test_blank_after_cleaning_is_invalid_field(self, client, raw):
        """Nothing was actually scanned (FR35)."""
        resp = client.post('/api/scan', json={'raw': raw})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'

    @pytest.mark.parametrize('raw', [
        12345,                                       # int - never coerced to '12345'
        None,                                        # explicit null
        ['a'],                                       # list
        {'raw': 'a'},                                # nested object
        True,                                        # bool
        1.5,                                         # float
    ])
    def test_non_string_raw_is_rejected_without_coercion(self, client, raw):
        """A non-str `raw` is a malformed client, not a scan."""
        resp = client.post('/api/scan', json={'raw': raw})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'

    def test_non_object_json_body_is_400_not_500(self, client):
        """A JSON array body must not raise."""
        resp = client.post('/api/scan', json=['not', 'a', 'dict'])
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'

    @pytest.mark.parametrize('body, content_type', [
        (b'', 'application/json'),                   # empty body
        (b'not json at all', 'application/json'),    # invalid JSON
        (b'{"raw": ', 'application/json'),           # truncated JSON
        (b'raw=0123', 'application/x-www-form-urlencoded'),  # wrong content type
        (b'', None),                                 # no body, no content type
    ])
    def test_absent_or_invalid_json_body_is_400_not_500(self, client, body, content_type):
        """`request.get_json(silent=True)` never lets a bad body become a 500."""
        headers = {'Content-Type': content_type} if content_type else {}
        resp = client.post('/api/scan', data=body, headers=headers)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'

    def test_at_the_length_limit_is_accepted(self, client):
        """Exactly MAX_SCAN_LENGTH characters is a valid scan."""
        raw = 'x' * MAX_SCAN_LENGTH
        resp = client.post('/api/scan', json={'raw': raw})
        assert resp.status_code == 200
        assert resp.get_json()['raw'] == raw

    def test_over_length_scan_is_rejected_naming_the_limit(self, client):
        """One character past the limit is refused, not echoed back."""
        resp = client.post('/api/scan', json={'raw': 'x' * (MAX_SCAN_LENGTH + 1)})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error']['code'] == 'invalid_field'
        assert data['error']['field'] == 'raw'
        assert str(MAX_SCAN_LENGTH) in data['error']['message']

    def test_outer_whitespace_counts_toward_the_length_limit(self, client):
        """The bound is checked BEFORE trimming, deliberately.

        It bounds the payload the client actually sent, not the scan hiding
        inside it, so a mostly-padding body is refused even though its content
        is nine characters. Pinned because the check's position relative to
        `_clean_scan_input` is otherwise invisible.
        """
        padded = ' ' * MAX_SCAN_LENGTH + 'STOCKCODE'
        resp = client.post('/api/scan', json={'raw': padded})
        assert resp.status_code == 400
        assert resp.get_json()['error']['field'] == 'raw'

        # ...and the same content, unpadded, is a perfectly good scan.
        assert client.post(
            '/api/scan', json={'raw': 'STOCKCODE'}).get_json()['raw'] == 'STOCKCODE'

    def test_max_scan_length_is_4096(self):
        """The documented bound; changing it is a deliberate contract change."""
        assert MAX_SCAN_LENGTH == 4096

    def test_get_is_not_allowed(self, client):
        """POST only — the scan is a submission, never a bookmarkable URL."""
        assert client.get('/api/scan').status_code == 405

    def test_endpoint_is_csrf_exempt(self):
        """Matches every other JSON route in routes.py; no CSRF token, no
        <meta name="csrf-token"> reader on the client side.

        Flask-WTF exposes no public exemption query, so this reads its
        registry — but derives the key from the view function rather than
        hardcoding a module path a rename would silently invalidate.
        """
        from app import csrf
        from app.main.routes import api_scan

        assert f'{api_scan.__module__}.{api_scan.__name__}' in csrf._exempt_views

    def test_csrf_exemption_holds_with_protection_actually_enabled(self, test_storage):
        """Behavioral proof the registry check above cannot give.

        `TestConfig` sets `WTF_CSRF_ENABLED = False` (config.py:77), so the
        `client` fixture would accept a tokenless POST whether or not the route
        carries `@csrf.exempt`. Build an app with protection genuinely on, and
        prove it is on with a control route before trusting the 200.
        """
        from app import create_app
        from config import TestConfig

        class CsrfEnabledConfig(TestConfig):
            WTF_CSRF_ENABLED = True

        app = create_app(CsrfEnabledConfig, storage_backend=test_storage)

        @app.route('/__csrf_control__', methods=['POST'])
        def _csrf_control():                       # pragma: no cover - never reached
            return 'reached'

        client = app.test_client()

        # Control: an unexempted route in this same app IS rejected, so the
        # protection is real and the assertion below means something.
        assert client.post('/__csrf_control__').status_code == 400

        resp = client.post('/api/scan', json={'raw': '0123'})
        assert resp.status_code == 200
        assert resp.get_json()['raw'] == '0123'

    def test_endpoint_resolves_through_the_catalog_service_exactly_once(
            self, client, monkeypatch):
        """Story 4.5 replaces 4.1's `test_endpoint_constructs_no_catalog_service`.

        That test was written to turn red exactly here, and this is its
        successor: the endpoint now resolves, and it does so through ONE
        `resolve_scan` call — the read-only seam AD-5 names. A second call would
        mean the route classified or looked something up on its own.
        """
        calls = []
        original = CatalogService.resolve_scan

        def _spy(self, raw):
            calls.append(raw)
            return original(self, raw)

        monkeypatch.setattr(CatalogService, 'resolve_scan', _spy)

        assert client.post('/api/scan', json={'raw': '0123'}).status_code == 200
        assert calls == ['0123']

    def test_response_has_exactly_the_six_envelope_keys(self, client):
        """The exact-shape gate, moved from three keys to six.

        Story 4.1's `test_response_has_no_resolution_fields` pinned
        `{success, raw, outcome}`; the routed envelope is that plus `kind`,
        `url` and `hit_count`, and nothing else — a consumer (Epic 7's capture
        path, Epic 9's scan view) reads this shape, so growth is deliberate.
        """
        data = client.post('/api/scan', json={'raw': '0123'}).get_json()
        assert set(data.keys()) == {
            'success', 'raw', 'kind', 'outcome', 'url', 'hit_count'}

    def test_the_endpoint_writes_nothing(self, client, test_storage, product_ids):
        """`POST /api/scan` stays read-only, whatever it resolves to (AD-5).

        This is what keeps the `@csrf.exempt` above defensible and what makes a
        rescan after the client's timeout free: a scan that lands on a create
        form has created nothing, and one that lands on a product has recorded
        no purchase and attached no identifier. Every mutation this story adds
        is behind an ordinary CSRF-protected form POST.
        """
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='untouched')
        svc.add_identifier(pid, identifier_type=IdentifierType.GTIN.value,
                           value=GTIN13)

        for raw in (GTIN13, GTIN_UNSTORED, 'NOTHING-MATCHES-THIS',
                    _envelope(f'1P{MPN}', 'Q10')):
            assert client.post('/api/scan', json={'raw': raw}).status_code == 200

        # Nothing created, nothing recorded, nothing attached.
        assert product_ids() == {pid}
        assert svc.get_purchases_for_product(pid) == []
        assert len(svc.get_identifiers_for_product(pid)) == 2  # GTIN + derived INTERNAL


@pytest.mark.unit
class TestScanRoutingOutcomes:
    """Every routing row of the Story 4.5 I/O & Edge-Case matrix (FR36/FR39/FR40).

    Real products through `test_storage`, no mocks: the whole point of moving
    the routing decision into the route is that it is assertable from a unit
    test with no browser.
    """

    def test_internal_label_matching_a_product_lands_on_it(self, client, test_storage):
        """FR36 rule 1: a label this shop printed lands on the record."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Internal-labelled part')
        internal_id = svc.get_product(pid).internal_id

        data = client.post('/api/scan',
                           json={'raw': _internal_scan(internal_id)}).get_json()

        assert data['kind'] == ScanKind.INTERNAL.value
        assert data['outcome'] == 'product'
        assert data['hit_count'] == 0
        assert _path(data['url']) == f'/products/{pid}'
        # An internal scan infers no identifier type and carries no receipt
        # fields, so `description` — the scan itself — is the only thing the
        # banner can hand the "create a separate product instead" link. Without
        # it that link is the one create form that opens with nothing on it,
        # while the SAME scan missing its lookup pre-fills `description` (FR40).
        assert _query(data['url']) == {
            'scan_kind': 'internal',
            'description': _internal_scan(internal_id),
        }

    def test_a_matched_internal_label_keeps_the_scan_on_the_duplicate_link(
            self, client, test_storage):
        """FR40 through FR41's create-anyway path: the scan is not lost because
        it happened to match."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Internal-labelled part')
        internal_id = svc.get_product(pid).internal_id

        data = client.post('/api/scan',
                           json={'raw': _internal_scan(internal_id)}).get_json()
        page = client.get(data['url'])
        assert page.status_code == 200

        create_link = _create_link(page.data.decode())
        assert _query(create_link)['description'] == _internal_scan(internal_id)
        assert _query(create_link)['duplicate_of'] == str(pid)

    def test_gtin_matching_a_product_lands_on_it_with_the_identifier(
            self, client, test_storage):
        """FR41: a matched GTIN carries what the duplicate link would need.

        `scan_kind` is the lower-case ScanKind wire value; `scan_type` is the
        UPPER-case IdentifierType value, because it feeds `identifier_type` on
        the "create a separate product instead" link.
        """
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='EAN-13 part')
        svc.add_identifier(pid, identifier_type=IdentifierType.GTIN.value,
                           value=GTIN13)

        data = client.post('/api/scan', json={'raw': GTIN13}).get_json()

        assert data['kind'] == ScanKind.GTIN.value
        assert data['outcome'] == 'product'
        assert _path(data['url']) == f'/products/{pid}'
        assert _query(data['url']) == {'scan_kind': 'gtin', 'scan_type': 'GTIN',
                                       'scan_value': GTIN13_KEY}

    def test_gtin_with_no_product_but_hits_lands_on_search(self, client, test_storage):
        """The fallthrough happens within the same scan (FR36).

        The search URL carries the create pre-fill too, so "Create a new
        product" from a results page keeps the scan's identifier.
        """
        svc = CatalogService(test_storage)
        for n in range(3):
            svc.create_product(description=f'carton {UPCA} #{n}')

        data = client.post('/api/scan', json={'raw': UPCA}).get_json()

        assert data['kind'] == ScanKind.GTIN.value
        assert data['outcome'] == 'search'
        assert data['hit_count'] == 3
        assert _path(data['url']) == '/products/search'
        assert _query(data['url']) == {'q': UPCA, 'identifier_type': 'GTIN',
                                       'identifier_value': UPCA_KEY}

    def test_gtin_matching_nothing_anywhere_lands_on_a_prefilled_create_form(
            self, client, test_storage):
        """FR40: a scan matching nothing opens a create form with the identifier
        attached and its type inferred — never an error page."""
        data = client.post('/api/scan', json={'raw': GTIN_UNSTORED}).get_json()

        assert data['kind'] == ScanKind.GTIN.value
        assert data['outcome'] == 'create'
        assert data['hit_count'] == 0
        assert _path(data['url']) == '/products/add'
        assert _query(data['url']) == {'identifier_type': 'GTIN',
                                       'identifier_value': GTIN_UNSTORED_KEY}

    def test_ecia_label_with_no_product_prefills_mpn_quantity_and_order(
            self, client, test_storage):
        """FR39: a distributor scan pre-fills MPN, quantity and order references.

        Every value arrives `.strip()`ed — the parser keeps them verbatim, and a
        padded value saved into `products.mpn` would carry its padding forever.
        """
        raw = _envelope(f'1P  {MPN}  ', f'P{CUSTOMER_MPN}', 'Q 25 ', 'KPO-4471')

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['kind'] == ScanKind.ECIA.value
        assert data['outcome'] == 'create'
        assert _path(data['url']) == '/products/add'
        assert _query(data['url']) == {'mpn': MPN, 'vendor_sku': CUSTOMER_MPN,
                                       'quantity': '25', 'order_number': 'PO-4471'}
        # No date is pre-filled: 9D/10D are YYWW, a week with no day in it.
        assert 'order_date' not in data['url']

    def test_ecia_label_matching_a_product_offers_the_purchase(
            self, client, test_storage):
        """FR41: a matched distributor scan lands on the record with the receipt
        data the "Add a purchase" link needs."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Resistor reel', mpn=MPN)

        raw = _envelope(f'1P{MPN}', f'P{CUSTOMER_MPN}', 'Q100', 'K PO-9')
        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] == 'product'
        assert _path(data['url']) == f'/products/{pid}'
        # `mpn` rides along too, for the "create a separate product instead"
        # link — the field FR39 names first, which that link would otherwise
        # open blank on. It is NOT put on the purchase link: Purchase has no
        # such column.
        assert _query(data['url']) == {'scan_kind': 'ecia', 'mpn': MPN,
                                       'quantity': '100',
                                       'order_number': 'PO-9',
                                       'vendor_sku': CUSTOMER_MPN}

    def test_free_text_matching_nothing_prefills_the_description(self, client):
        """The scan is not lost: free text infers no identifier type, so the raw
        scan is preserved where the operator can see it (FR40)."""
        data = client.post('/api/scan', json={'raw': 'WIDGET-9'}).get_json()

        assert data['kind'] == ScanKind.FREE_TEXT.value
        assert data['outcome'] == 'create'
        assert _path(data['url']) == '/products/add'
        assert _query(data['url']) == {'description': 'WIDGET-9'}

    def test_a_degraded_envelope_routes_instead_of_raising(self, client):
        """NFR8: a valid header with an unreadable body is already `free_text`,
        and it routes on the raw scan rather than erroring."""
        raw = '[)>\x1e06\x1d\x1e\x04'

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['kind'] == ScanKind.FREE_TEXT.value
        assert data['outcome'] in {'search', 'create'}
        assert data['url']

    @pytest.mark.parametrize('raw', [
        UPCA_KEY,                                    # gtin
        'plain free text',                           # free_text
        '[)>\x1e06\x1d1PABC\x1dQ10\x1d\x1e\x04',     # ecia
        '\x00' * 8,                                  # unstorable text
        ' [)>\x1e06\x1d\x1e\x04',                    # a degraded envelope
    ], ids=['gtin', 'free_text', 'ecia', 'nul_run', 'degraded'])
    def test_no_scan_dead_ends(self, client, raw):
        """FR36/FR40, stated as one property: there is no input for which the
        operator is left where they were or shown an error page."""
        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] in {'product', 'search', 'create'}
        assert isinstance(data['url'], str) and data['url'].startswith('/')

    def test_a_failing_resolution_is_the_ad13_envelope_not_an_exception(
            self, client, monkeypatch):
        """A broken `GS1_INTERNAL_*` grammar or a database outage is a 500 the
        client toasts — never an HTML error page, and never a navigation.

        The only mock in this file's routing tests, and unavoidable: no scan
        input can make `resolve_scan` raise (NFR8 is exactly that promise), so
        the failure has to be injected.
        """
        def _boom(self, raw):
            raise RuntimeError('database is gone')

        monkeypatch.setattr(CatalogService, 'resolve_scan', _boom)

        resp = client.post('/api/scan', json={'raw': '0123'})
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False
        assert isinstance(data['error'], dict)       # AD-13 object envelope
        assert data['error']['code'] == 'server_error'
        assert 'url' not in data


@pytest.mark.unit
class TestSearchTextAgreesWithTheResolver:
    """The route re-derives the text the resolver searched; this pins the two.

    AD-15 freezes `ScanResolution` to three fields, so the searched text is not
    returned and a fourth field must not be added — the route therefore carries
    a SECOND copy of a service-internal rule in `_scan_search_text`. That is
    only safe if a change to either side turns a test red, which is what this
    class is: for every `ScanKind`, `search_products(_scan_search_text(c))`
    returns exactly the hits `resolve_scan` counted, so the search page can
    never show a different set than `hit_count` promised.

    Every vector below is storable text that MISSES its lookup, because those
    are the scans that reach a search at all.
    """

    def _agree(self, service, raw, expected_kind):
        resolution = service.resolve_scan(raw)
        assert resolution.classification.kind is expected_kind
        assert resolution.product is None, 'vector must miss its lookup'

        search_text = _scan_search_text(resolution.classification)
        rederived = service.search_products(search_text)
        # Compared by id: a resolution holds detached ORM rows whose __eq__ is
        # identity, so two queries for the same product are never equal.
        assert [p.id for p in rederived] == [p.id for p in resolution.free_text_hits]

        # ...and again through the transform that actually SHIPS. The derivation
        # rule is only half the promise: what the operator's browser sends back
        # is `_scan_url_value('q', …)`, so a rule that agreed here and a `q`
        # sanitizer that quietly changed it would still land them on a different
        # set than `hit_count` counted. (The other shipped transform,
        # `_bounded_scan_url`'s halving, is length-only and is pinned
        # separately; every vector here is far inside its budget.)
        shipped = service.search_products(_scan_url_value('q', search_text))
        assert [p.id for p in shipped] == [p.id for p in resolution.free_text_hits]
        return resolution

    def test_internal_miss_searches_the_token_stripped_id(self, test_storage):
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Reachable only by its id')
        internal_id = svc.get_product(pid).internal_id
        # A different product carrying the id in its text, so the fallthrough
        # search has something to find and the comparison is not [] == [].
        svc.create_product(description=f'spare for {internal_id}')

        # Scanned with a DIFFERENT id than any product holds, so the exact
        # lookup misses while the search still runs on the bare id.
        resolution = self._agree(svc, _internal_scan('ZZZZZZZZZZ'),
                                 ScanKind.INTERNAL)
        assert _scan_search_text(resolution.classification) == 'ZZZZZZZZZZ'

    def test_gtin_miss_searches_the_aim_stripped_raw_not_the_key(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description=f'carton {UPCA}')

        resolution = self._agree(svc, UPCA, ScanKind.GTIN)
        # The raw digits as scanned, NOT the normalized 14 — the key was just
        # looked up exactly, so re-searching it would add nothing.
        assert _scan_search_text(resolution.classification) == UPCA
        assert resolution.free_text_hits

    def test_ecia_miss_searches_the_first_non_blank_part_number(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description=f'reel labelled {MPN}')

        resolution = self._agree(svc, _envelope(f'1P {MPN} ', f'P{CUSTOMER_MPN}'),
                                 ScanKind.ECIA)
        assert _scan_search_text(resolution.classification) == MPN
        assert resolution.free_text_hits

    def test_ecia_with_no_part_number_searches_nothing(self, test_storage):
        """The resolver issues no query at all for a quantity-only envelope, so
        the re-derived text must be one `search_products` answers `[]` to."""
        svc = CatalogService(test_storage)
        svc.create_product(description='some product')

        resolution = self._agree(svc, _envelope('Q10', '9D2612'), ScanKind.ECIA)
        assert _scan_search_text(resolution.classification) == ''
        assert resolution.free_text_hits == ()

    def test_free_text_searches_the_aim_stripped_raw(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description='a WIDGET-9 in a box')

        resolution = self._agree(svc, ']d2WIDGET-9', ScanKind.FREE_TEXT)
        assert _scan_search_text(resolution.classification) == 'WIDGET-9'
        assert scan_router.strip_aim_prefix(']d2WIDGET-9') == 'WIDGET-9'
        assert resolution.free_text_hits

    def test_the_hit_count_the_endpoint_reports_is_the_set_the_page_shows(
            self, client, test_storage):
        """The two halves joined end to end: what `hit_count` promised is what
        `/products/search` renders when the operator follows `url`."""
        svc = CatalogService(test_storage)
        for n in range(4):
            svc.create_product(description=f'SHARED-TOKEN part {n}')

        data = client.post('/api/scan', json={'raw': 'SHARED-TOKEN'}).get_json()
        assert data['outcome'] == 'search'
        assert data['hit_count'] == 4

        page = client.get(data['url'])
        assert page.status_code == 200
        body = page.data.decode()
        for n in range(4):
            assert f'SHARED-TOKEN part {n}' in body


@pytest.mark.unit
class TestScanLogging:
    """The only server-side record that a scan arrived.

    Pinned rather than merely present: this is the one endpoint whose entire
    purpose is "did the scan get here", so a log line that can be deleted
    without turning a test red is a diagnostic that will quietly disappear.
    """

    def test_captured_scan_is_logged_with_its_bytes(self, client, app, caplog):
        """`repr`, not a character count - a wedge investigation asks which
        bytes actually arrived, and control characters are invisible otherwise.
        """
        with caplog.at_level(logging.DEBUG, logger=app.logger.name):
            assert client.post('/api/scan', json={'raw': 'P\x1d123'}).status_code == 200

        captured = [r.getMessage() for r in caplog.records if 'Scan captured' in r.getMessage()]
        assert captured, 'a captured scan must leave a server-side record'
        assert '\\x1d' in captured[0]

    @pytest.mark.parametrize('body, fragment', [
        ({'raw': '   '}, 'blank after trimming'),          # scanner emitting only its suffix
        ({'raw': 'x' * (MAX_SCAN_LENGTH + 1)}, 'exceeds'),  # runaway payload
        ({}, 'not a string'),                              # malformed client
    ])
    def test_every_rejection_path_logs_a_warning(self, client, app, caplog, body, fragment):
        """A rejected scan the operator has to ask about must be findable."""
        with caplog.at_level(logging.DEBUG, logger=app.logger.name):
            assert client.post('/api/scan', json=body).status_code == 400

        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(fragment in message for message in warnings), warnings

    def test_logged_scan_is_bounded(self, client, app, caplog):
        """The endpoint is CSRF-exempt and unthrottled, and `repr` of control
        characters is several times longer than the payload - so what reaches
        the log is truncated rather than echoed at whatever length was sent.
        """
        raw = 'y' * MAX_SCAN_LENGTH
        with caplog.at_level(logging.DEBUG, logger=app.logger.name):
            assert client.post('/api/scan', json={'raw': raw}).status_code == 200

        captured = [r.getMessage() for r in caplog.records if 'Scan captured' in r.getMessage()]
        assert captured
        assert 'y' * (_SCAN_LOG_CHARS + 1) not in captured[0]
        assert str(MAX_SCAN_LENGTH) in captured[0]      # the true length is still recorded


@pytest.mark.unit
class TestTheRoutedUrlIsAlwaysBuildable:
    """A scan must not be able to break URL BUILDING itself.

    `_scan_destination` feeds scan-derived text to `url_for`, so anything the
    scan can carry that werkzeug's percent-encoder or the transport in front of
    Flask refuses would turn a scan `resolve_scan` handled cleanly into a 500 or
    an error page — the dead end this endpoint's whole contract denies (FR36).
    """

    def test_a_lone_surrogate_routes_instead_of_500ing(self, client):
        """The vector Story 4.1's comments already name.

        werkzeug percent-encodes a query value with `errors='strict'`, so an
        unsanitized lone surrogate raises `UnicodeEncodeError` inside `url_for`,
        the blanket handler catches it and the operator gets a 500 for a scan
        that classified and resolved without complaint.
        """
        resp = client.post('/api/scan', json={'raw': '\ud800ABC'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['outcome'] in {'product', 'search', 'create'}
        assert data['url'].startswith('/')
        # The scan is not lost either: what could be represented is still there.
        assert 'ABC' in data['url']

    @pytest.mark.parametrize('raw', [
        '\ud800' * 2048,                       # nothing but lone surrogates
        '\ud800' + 'A' * 4095,                 # one, leading
        'A' * 4095 + '\udfff',                 # one, trailing
    ], ids=['all_surrogates', 'leading', 'trailing'])
    def test_no_surrogate_shape_reaches_the_500_path(self, client, raw):
        assert client.post('/api/scan', json={'raw': raw}).status_code == 200

    @pytest.mark.parametrize('raw', [
        'A' * MAX_SCAN_LENGTH,                                   # free text
        'é' * MAX_SCAN_LENGTH,                              # 2-byte UTF-8
        '\U0001f600' * MAX_SCAN_LENGTH,                          # 4-byte UTF-8
        '[)>\x1e06\x1d1P' + 'X' * 2000 + '\x1dK' + 'Y' * 2000 + '\x1d\x1e\x04',
    ], ids=['ascii', 'latin1', 'astral', 'ecia'])
    def test_a_max_length_scan_produces_a_transportable_url(self, client, raw):
        """`MAX_SCAN_LENGTH` is 4096 and the search arm puts scan text into the
        URL TWICE, which measured 10-12 KB — past gunicorn's 8190-byte request
        line and nginx's default 8 KB header buffer, so the browser lands on a
        414 or a 400 instead of on the results page.

        The Flask test client imposes no request-line limit of its own, so the
        property has to be asserted on the generated URL directly.
        """
        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['url'].startswith('/')
        assert len(data['url']) < 8000, len(data['url'])

    def test_a_prefill_is_capped_at_the_column_it_targets(self, client):
        """Bounded per value, not merely in total: every pre-fill lands in a
        column, and a value past that column's limit could not be saved."""
        data = client.post('/api/scan', json={'raw': 'W' * 1000}).get_json()

        assert data['outcome'] == 'create'
        assert _query(data['url'])['description'] == 'W' * 255

    def test_the_search_url_carries_a_bounded_q(self, client, test_storage):
        """`q` is bounded, and the bound is the URL budget rather than a column:
        the only searched column that can hold more is `products.notes` (TEXT).

        Truncating `q` is NOT the harmless narrowing it looks like — see
        `test_a_truncatable_q_does_not_evict_the_hits_it_counted` — so the bound
        is set past every VARCHAR the fallthrough search touches.
        """
        long_text = 'SHARED' + 'Z' * 2000
        CatalogService(test_storage).create_product(
            description='Long-noted product', notes=long_text)

        data = client.post('/api/scan', json={'raw': long_text}).get_json()

        assert data['outcome'] == 'search'
        assert len(_query(data['url'])['q']) <= 1024
        page = client.get(data['url'])
        assert page.status_code == 200

    def test_a_truncatable_q_does_not_evict_the_hits_it_counted(
            self, client, test_storage):
        """The results page must show the products `hit_count` counted.

        A shortened `q` matches a SUPERSET, which reads as safe — but
        `search_products` then keeps only the first 50 rows in ascending
        `products.id`, so the superset's extra LOW-id members evict the genuine
        matches and the page shows 50 products, none of them the ones the
        endpoint counted. Reproduced here at the length that used to be cut: 60
        products matching only the leading 255 characters, three matching the
        whole scan.
        """
        svc = CatalogService(test_storage)
        prefix = 'PFX' + 'A' * 300
        for i in range(60):
            svc.create_product(description=f'Decoy {i}', notes=prefix)
        wanted = []
        for i in range(3):
            wanted.append(svc.create_product(description=f'Wanted {i}',
                                             notes=prefix + 'TAIL'))

        data = client.post('/api/scan', json={'raw': prefix + 'TAIL'}).get_json()

        assert data['outcome'] == 'search'
        assert data['hit_count'] == 3
        page = client.get(data['url'])
        assert page.status_code == 200
        for i in range(3):
            assert f'Wanted {i}'.encode() in page.data
        assert b'Decoy 0' not in page.data
        assert len(wanted) == 3

    @pytest.mark.parametrize('raw', ['AB\x00CD', 'AB\x1fCD', 'AB\x7fCD'],
                             ids=['nul', 'unit_separator', 'del'])
    def test_control_characters_never_reach_a_prefill(self, client, raw):
        """A wedge can deliver a control character, and an `<input>` cannot
        render one: it would pre-fill `description` — the one required field on
        the create form — with bytes the operator can neither see nor delete.
        They become spaces, which is what a human reads off the label."""
        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] == 'create'
        assert _query(data['url'])['description'] == 'AB CD'

    def test_q_keeps_the_control_characters_a_prefill_loses(
            self, client, test_storage):
        """`q` is exempt from that substitution, and has to be: it is re-searched
        rather than rendered, so a `q` that differs by even one character from
        the text the resolver searched shows a different set of products from the
        one `hit_count` counted."""
        raw = 'SEP\x1fARATED'
        CatalogService(test_storage).create_product(description=raw)

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] == 'search'
        assert data['hit_count'] == 1
        assert _query(data['url'])['q'] == raw
        assert _query(data['url'])['description'] == 'SEP ARATED'


@pytest.mark.unit
class TestEciaPrefillEdgeCases:
    """The two ECIA envelopes whose pre-fill would otherwise be unusable."""

    def test_a_date_only_envelope_keeps_the_scan_in_the_description(self, client):
        """`9D`/`10D` are YYWW and are deliberately never coerced into a date,
        so an envelope carrying only them yields an EMPTY pre-fill — and an
        entirely blank create form would lose the scanned text, which is what
        FR40 forbids. It falls back to the `internal`/`free_text` rule."""
        raw = _envelope('9D2612', '10D2614')

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['kind'] == ScanKind.ECIA.value
        assert data['outcome'] == 'create'
        query = _query(data['url'])
        # The envelope's own separators are spaces by the time they reach a form
        # input, so the records stay readable rather than running together.
        assert '9D2612' in query['description']
        assert '10D2614' in query['description']
        assert not any(ord(ch) < 0x20 for ch in query['description'])
        assert 'order_date' not in query and 'received_date' not in query

    @pytest.mark.parametrize('record, field, value', [
        ('Q25', 'quantity', '25'),
        ('KPO-9', 'order_number', 'PO-9'),
    ], ids=['quantity_only', 'order_only'])
    def test_an_envelope_naming_no_part_still_keeps_the_scan(
            self, client, record, field, value):
        """An envelope carrying a quantity or an order number but NO part number
        pre-filled only that one field and left `description` — the one required
        field — blank, with the scanned label nowhere on the page. The date-only
        case was fixed by an empty-pre-fill fallback, which these shapes slip
        past: the rule is "the pre-fill names no part", not "it is empty"."""
        raw = _envelope(record)

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['kind'] == ScanKind.ECIA.value
        assert data['outcome'] == 'create'
        query = _query(data['url'])
        assert query[field] == value          # what the label did carry
        assert query['description']           # and the scan itself, not lost
        assert 'mpn' not in query

    @pytest.mark.parametrize('quantity', ['0', '1.5K', 'abc', '-3', '1_0', '٥',
                                          '99999999999999'])
    def test_an_unusable_quantity_is_not_prefilled(self, client, quantity):
        """A pre-filled value the form then refuses is a validation error on a
        field the operator never typed. `Q0` and a scaled quantity like `1.5K`
        are both real on real labels."""
        raw = _envelope(f'1P{MPN}', f'Q{quantity}')

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['kind'] == ScanKind.ECIA.value
        query = _query(data['url'])
        assert query['mpn'] == MPN            # the rest of the label survives
        assert 'quantity' not in query

    def test_a_usable_quantity_still_is(self, client):
        raw = _envelope(f'1P{MPN}', 'Q 42 ')

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert _query(data['url'])['quantity'] == '42'

    def test_a_matched_ecia_label_carries_the_mpn_onto_the_product(
            self, client, test_storage):
        """FR39 names the MPN first. The detail page puts it on the "create a
        separate product instead" link, so without it that link opens blank on
        the one field the operator just scanned off the label."""
        svc = CatalogService(test_storage)
        pid = svc.create_product(description='Resistor reel', mpn=MPN)

        raw = _envelope(f'1P{MPN}', 'Q100', 'KPO-9')
        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] == 'product'
        assert _path(data['url']) == f'/products/{pid}'
        assert _query(data['url'])['mpn'] == MPN

        # ...and it reaches the duplicate link on the page itself.
        page = client.get(data['url'])
        assert page.status_code == 200
        assert f'mpn={MPN}' in page.data.decode()
