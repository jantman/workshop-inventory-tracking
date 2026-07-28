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

The trim rule itself is no longer tested here. It moved to
`app/utils/scan_input.py` (DW-59) and its assertions moved with it to
`tests/unit/test_scan_input.py`; what stays is the endpoint's own conduct — the
length refusal, the blank refusal, the log lines — which is transport behavior
that merely depends on the rule.

Uses the `client` fixture, with real products created through `CatalogService`
against the shared `test_storage` — no mocking of the service or the ORM. The
two exceptions are labelled where they appear: the CSRF test builds a second app
with protection genuinely enabled, and the 500-path test needs a `resolve_scan`
that raises, which no input can produce.
"""

import logging
import re
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlparse

import pytest
from flask import url_for

from app.mariadb_catalog_service import CatalogService
from app.main.routes import (_MAX_SCAN_URL_CHARS, _SCAN_LOG_CHARS,
                             _SCAN_URL_Q_FLOOR, _SCAN_URL_Q_LIMIT,
                             _URL_QUERY_SAFE, _bounded_scan_url,
                             _scan_url_value)
from app.models import IdentifierType, ScanKind
from app.utils import scan_router
from app.utils.scan_input import MAX_SCAN_LENGTH
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
        `clean_scan_input` is otherwise invisible.
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

    def test_the_wedge_no_read_is_not_routed_as_a_trade_item_number(
            self, client, test_storage):
        """DW-69, end to end. An all-zero run passes mod-10, so before the
        refusal in `gtin.py` this scan answered `kind: gtin` and pre-filled the
        create form with `identifier_type=GTIN, identifier_value=
        00000000000000` — a meaningless number the operator would have saved
        onto a real product. It is now free text, so it pre-fills `description`
        instead and attaches no identifier."""
        data = client.post('/api/scan', json={'raw': '00000000'}).get_json()

        assert data['kind'] == ScanKind.FREE_TEXT.value
        assert data['outcome'] == 'create'
        assert _path(data['url']) == '/products/add'
        # Exact equality, not two `not in` checks: it pins the ABSENCE of
        # `identifier_type`/`identifier_value` and every other key at once.
        assert _query(data['url']) == {'description': '00000000'}

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
        '0' * 8,                                     # the wedge no-read
    ], ids=['gtin', 'free_text', 'ecia', 'nul_run', 'degraded', 'no_read'])
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
    """The route asks the service which text the resolver searched; this pins it.

    AD-15 freezes `ScanResolution` to three fields, so the searched text is not
    returned and a fourth field must not be added. The route used to re-derive
    it — a SECOND copy of a service-internal rule — which was possible only
    while the rule was a pure function of the classification. The `ecia` arm's
    per-candidate fallthrough made the winning candidate a function of the
    DATABASE, so the rule moved into `CatalogService.scan_search_text` and the
    route calls it. This class is what makes that one implementation
    trustworthy: for every `ScanKind`,
    `search_products(scan_search_text(resolution))` returns exactly the hits
    `resolve_scan` counted, so the search page can never show a different set
    than `hit_count` promised.

    Every vector below is storable text that MISSES its lookup, because those
    are the scans that reach a search at all.
    """

    def _agree(self, service, raw, expected_kind):
        resolution = service.resolve_scan(raw)
        assert resolution.classification.kind is expected_kind
        assert resolution.product is None, 'vector must miss its lookup'

        search_text = service.scan_search_text(resolution)
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
        assert svc.scan_search_text(resolution) == 'ZZZZZZZZZZ'

    def test_gtin_miss_searches_the_aim_stripped_raw_not_the_key(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description=f'carton {UPCA}')

        resolution = self._agree(svc, UPCA, ScanKind.GTIN)
        # The raw digits as scanned, NOT the normalized 14 — the key was just
        # looked up exactly, so re-searching it would add nothing.
        assert svc.scan_search_text(resolution) == UPCA
        assert resolution.free_text_hits

    def test_ecia_miss_searches_the_first_non_blank_part_number(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description=f'reel labelled {MPN}')

        resolution = self._agree(svc, _envelope(f'1P {MPN} ', f'P{CUSTOMER_MPN}'),
                                 ScanKind.ECIA)
        assert svc.scan_search_text(resolution) == MPN
        assert resolution.free_text_hits

    def test_ecia_miss_reached_only_by_the_second_part_number(self, test_storage):
        """The ECIA shape that is the whole reason the rule moved into the
        service, and the one the class was missing.

        The vector above is a FIRST-candidate win, which the route's deleted
        pure duplicate could already compute — it always answered
        `candidates[0]`. Here `1P` finds nothing and `P` does, so `q` must be
        `P`, and only a rule that re-establishes the winner against the DATABASE
        can say so. `_agree` runs it through the shipped `_scan_url_value('q',
        …)` transform as well, so the value the operator's browser sends back is
        pinned, not just the derivation."""
        svc = CatalogService(test_storage)
        svc.create_product(description=f'reel labelled {CUSTOMER_MPN}')

        resolution = self._agree(svc, _envelope('1PSUP-99999', f'P{CUSTOMER_MPN}'),
                                 ScanKind.ECIA)
        assert svc.scan_search_text(resolution) == CUSTOMER_MPN
        assert len(resolution.free_text_hits) == 1

    def test_ecia_with_no_part_number_searches_nothing(self, test_storage):
        """The resolver issues no query at all for a quantity-only envelope, so
        the re-derived text must be one `search_products` answers `[]` to."""
        svc = CatalogService(test_storage)
        svc.create_product(description='some product')

        resolution = self._agree(svc, _envelope('Q10', '9D2612'), ScanKind.ECIA)
        assert svc.scan_search_text(resolution) == ''
        assert resolution.free_text_hits == ()

    def test_free_text_searches_the_aim_stripped_raw(self, test_storage):
        svc = CatalogService(test_storage)
        svc.create_product(description='a WIDGET-9 in a box')

        resolution = self._agree(svc, ']d2WIDGET-9', ScanKind.FREE_TEXT)
        assert svc.scan_search_text(resolution) == 'WIDGET-9'
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

    def test_a_second_candidate_win_reaches_the_page_it_counted(
            self, client, test_storage):
        """The same end-to-end promise for the one ECIA shape no route could
        compute: the hits came from `P`, so `q` has to be `P`.

        Everything in between is real — `POST /api/scan` resolves, builds the
        URL from `scan_search_text`, and the browser follows it — so a `q` built
        from `candidates[0]` (which is what the deleted pure duplicate would
        have produced) would land the operator on a page showing NOTHING while
        `hit_count` promised three. Products carrying only the SECOND part
        number are what makes those two answers distinguishable."""
        svc = CatalogService(test_storage)
        for n in range(3):
            svc.create_product(description=f'reel {n} of {CUSTOMER_MPN}')
        # A product on the first candidate would make either rule pass, so
        # nothing here carries 'SUP-99999'.

        data = client.post('/api/scan', json={
            'raw': _envelope('1PSUP-99999', f'P{CUSTOMER_MPN}')}).get_json()
        assert data['outcome'] == 'search'
        assert data['hit_count'] == 3
        assert _query(data['url'])['q'] == CUSTOMER_MPN

        page = client.get(data['url'])
        assert page.status_code == 200
        body = page.data.decode()
        for n in range(3):
            assert f'reel {n} of {CUSTOMER_MPN}' in body

    def test_the_endpoint_opens_no_more_sessions_than_api_scan_claims(
            self, client, test_storage, monkeypatch):
        """The route-level ceiling `api_scan`'s cost paragraph states, pinned.

        FIVE for the worst case it names — a two-candidate ECIA envelope routed
        to `search`: two lookups and two searches inside `resolve_scan`, then
        ONE more when `_scan_destination` asks `scan_search_text` which
        candidate won (every candidate but the last, since with hits in hand the
        last needs no asking). The resolver's own ceiling of four is pinned in
        `tests/unit/test_scan_resolution.py`; this is the number that GREW when
        the searched-text rule moved into the service, and the one an
        unthrottled, CSRF-exempt POST actually costs — the reason the paragraph
        exists at all.

        The counter is installed by wrapping `__init__` rather than by patching
        one instance, because the route builds its own service through
        `_get_catalog_service()` and the fixture's is a different object. Only
        services constructed AFTER the patch are counted, so the setup above
        costs nothing.
        """
        svc = CatalogService(test_storage)
        svc.create_product(description=f'reel labelled {CUSTOMER_MPN}')

        opened = []
        real_init = CatalogService.__init__

        def counting_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            factory = self.Session

            def counting(*a, **kw):
                opened.append(1)
                return factory(*a, **kw)

            self.Session = counting

        monkeypatch.setattr(CatalogService, '__init__', counting_init)

        data = client.post('/api/scan', json={
            'raw': _envelope('1PSUP-99999', f'P{CUSTOMER_MPN}')}).get_json()

        assert data['outcome'] == 'search'
        assert data['hit_count'] == 1
        assert len(opened) == 5


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
        # Exactly the ceiling, not merely inside it. The interval this bound
        # lives in has two ends — `_SCAN_URL_Q_LIMIT` down to
        # `_SCAN_URL_Q_FLOOR` — and the claim the change rests on is that
        # neither end moves with the alphabet. `<= 1024` would stay green if
        # this ASCII scan were cut to the floor as an astral one is, which is
        # the whole failure the floor exists to make impossible.
        assert len(_query(data['url'])['q']) == _SCAN_URL_Q_LIMIT
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

    def test_an_astral_search_scan_still_leaves_q_on_the_floor(
            self, client, test_storage):
        """Where `q` is cut must not be a function of the scanned ALPHABET.

        One astral character percent-encodes to twelve, so a full
        `_SCAN_URL_Q_LIMIT` slice of astral text is 12288 characters — over the
        transport budget no matter what else is dropped, which means the
        shrinking loop always runs on this alphabet and never runs on ASCII.
        "Halve the longest until it fits" therefore cut `q` to ~256 here while
        leaving it at 1024 for the same-length Latin scan, re-opening the
        eviction DW-17 records at a bound nothing in the code states. The
        halving now stops at `_SCAN_URL_Q_FLOOR`, which is one number for every
        alphabet.
        """
        raw = '\U0001f600' * MAX_SCAN_LENGTH
        CatalogService(test_storage).create_product(
            description='Astral-noted product', notes=raw)

        data = client.post('/api/scan', json={'raw': raw}).get_json()

        assert data['outcome'] == 'search'
        assert data['url'].startswith('/')
        assert len(data['url']) <= _MAX_SCAN_URL_CHARS, len(data['url'])
        q = _query(data['url'])['q']
        assert len(q) == _SCAN_URL_Q_FLOOR, len(q)
        # And it has to ARRIVE, which is the whole point of the budget: the
        # ASCII case at `test_the_search_url_carries_a_bounded_q` follows its
        # URL and asserts a 200, and a bound the astral case only measures is
        # not the same claim (FR36/FR40 are about the page, not the string).
        assert client.get(data['url']).status_code == 200

    def test_every_prefill_is_shed_before_q_is_touched(self, app):
        """The arguments are not interchangeable, and the shrinking rule has to
        know it: a pre-fill lands in a form field the operator can retype, while
        `q` is the one value the results page is built from. So the pre-fills go
        first — halved, then dropped outright — and `q` is only cut once there
        is nothing left to shed.
        """
        with app.test_request_context():
            url = _bounded_scan_url('main.product_search',
                                    q='\U0001f600' * _SCAN_URL_Q_LIMIT,
                                    description='\U0001f600' * 255)

        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        assert 'description=' not in url        # dropped, not left empty
        assert len(_query(url)['q']) == _SCAN_URL_Q_FLOOR

    @pytest.mark.parametrize('q_length', [400, _SCAN_URL_Q_FLOOR],
                             ids=['under_the_floor', 'on_the_floor'])
    def test_a_q_already_at_the_floor_is_not_cut_to_pay_for_a_prefill(
            self, app, q_length):
        """The floor is a floor, not a target: a `q` that arrives at or under it
        is left alone and the pre-fill absorbs the whole overrun.

        Both ends of "at or under" are exercised. The "under" case was the only
        one covered, and it clears the second loop's `len(args['q']) >
        _SCAN_URL_Q_FLOOR` guard by a margin of 112 characters; a `q` of
        exactly `_SCAN_URL_Q_FLOOR` is where that comparison is actually
        decided, and it has to stay strict — `>=` could not shorten a floored
        `q` (the `max` clamp pins it at the floor), so it would re-evaluate an
        unchanged URL rather than terminate.
        """
        with app.test_request_context():
            url = _bounded_scan_url('main.product_search',
                                    q='\U0001f600' * q_length,
                                    description='\U0001f600' * 255)

        query = _query(url)
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        assert query['q'] == '\U0001f600' * q_length
        assert 0 < len(query['description']) < 255

    def test_a_floor_length_q_fits_the_budget_in_the_worst_alphabet(self, app):
        """The property the floor exists to guarantee: a `q` sitting on the
        floor, in the most expensive alphabet there is and with every other
        argument gone, is still transportable — so the halving never has to
        choose between honouring the floor and honouring the budget."""
        with app.test_request_context():
            url = _bounded_scan_url('main.product_search',
                                    q='\U0001f600' * _SCAN_URL_Q_FLOOR)

        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        assert _query(url)['q'] == '\U0001f600' * _SCAN_URL_Q_FLOOR

    def test_the_floor_arithmetic_holds_from_both_ends(self, app):
        """The same two constraints stated as arithmetic rather than as
        behaviour, so a later edit to any of the three constants has to face
        them: the floor must stay past the largest VARCHAR the fallthrough
        search touches (255), and a floored `q` must still fit the budget in
        the worst case."""
        worst_case_encoded_chars_per_character = 12     # 4 UTF-8 bytes, `%XX`
        with app.test_request_context():
            path = _path(_bounded_scan_url('main.product_search'))

        # Strict on both sides, and both strictnesses are load-bearing. A floor
        # OF 255 would let a cut `q` match a full-width `products.description`,
        # falsifying DW-17's "only through `products.notes`"; a floor EQUAL to
        # the limit would make the second loop's `> _SCAN_URL_Q_FLOOR` guard
        # unsatisfiable, so `q` would never be cut and an astral scan would ship
        # a 12288-character URL to a 414.
        assert _SCAN_URL_Q_FLOOR > 255
        assert _SCAN_URL_Q_FLOOR < _SCAN_URL_Q_LIMIT
        assert (_SCAN_URL_Q_FLOOR * worst_case_encoded_chars_per_character
                + len(path) + len('?q=')) <= _MAX_SCAN_URL_CHARS

    def test_a_non_search_arm_still_halves_its_costliest_prefill(self, app):
        """No `q` to protect, so the rest of the rule stands unchanged: the
        costliest pre-fill is halved until the URL fits and the cheap ones are
        left as they were."""
        with app.test_request_context():
            url = _bounded_scan_url('main.product_add',
                                    description='\U0001f600' * 1000,
                                    manufacturer='ACME')

        query = _query(url)
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        assert query['manufacturer'] == 'ACME'
        assert 0 < len(query['description']) < 1000

    def test_the_prefill_that_is_shed_is_the_one_that_costs_the_most(self, app):
        """Which pre-fill is shed is decided by percent-encoded cost, not by
        character count, and the two rank the real argument set differently.

        `_scan_url_args` caps each pre-fill at the column it targets, so a
        `category_path` may be twice as many CHARACTERS as a `description` while
        costing a sixth as much URL: 512 ASCII characters encode to 512, and 255
        astral ones to 3060. Ranked by characters the loop would cut the ASCII
        `category_path` — buying 256 characters of budget it did not need and
        mangling text the operator can read — while the astral values that
        actually caused the overrun sat untouched. Ranked by cost it leaves the
        cheap value whole and cuts the expensive one, which is why
        `category_path` comes back at its full 512 here.

        The three astral values are deliberately given DIFFERENT lengths. At
        equal lengths they cost exactly the same, `max` breaks the tie by
        argument order, and which of them survives is then a fact about how
        this call was written rather than about the ranking rule: reordering
        the keywords moves the surviving value with them. Distinct costs make
        the expected outcome unique, so the assertions below pin the rule.
        """
        with app.test_request_context():
            url = _bounded_scan_url('main.product_add',
                                    category_path='C' * 512,
                                    description='\U0001f600' * 255,
                                    manufacturer='\U0001f600' * 200,
                                    vendor_sku='\U0001f600' * 150)

        query = _query(url)
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        # 512 ASCII characters: the most CHARACTERS in the argument set and the
        # least URL, so this is the assertion the two metrics disagree on.
        assert query['category_path'] == 'C' * 512
        # Per value rather than as a sum: a total under the sum of the inputs
        # is satisfied by any shrinking of any ONE of them, which would not say
        # that the costliest is the one being cut. One halving of the costliest
        # value is enough here, so the two cheaper astral values are spared
        # whole — and would not be if the loop reached for either of them.
        assert 0 < len(query['description']) < 255
        assert query['manufacturer'] == '\U0001f600' * 200
        assert query['vendor_sku'] == '\U0001f600' * 150

    def test_cost_is_measured_with_the_encoder_that_builds_the_url(self, app):
        """"What it costs" has to be measured with werkzeug's query encoder,
        not with the obvious `quote(value, safe='')`.

        The two disagree on the two commonest characters in readable text:
        werkzeug writes a space as `+` and leaves `!$'()*,/:;?@` literal, all
        one character apiece, where `quote(safe='')` charges three for each. So
        spaced English and slash-heavy category paths are over-charged by up to
        3x, and a value can be ranked costliest while genuinely being the
        cheapest thing in the argument set -- which is the same cost-blindness
        as ranking by character count, only subtler.

        Here `description` is half spaces: 3000 characters that cost 3000, but
        that `quote(safe='')` scores at 6000, above the 1900 Cyrillic
        characters of `manufacturer` that really do cost 5700. Under the wrong
        metric `description` is halved first and comes back mangled; under the
        right one it is never touched and `manufacturer` absorbs the overrun
        alone. Values are sized past their column caps deliberately, and NOT
        because the ranking is unobservable at production sizes -- it plainly
        is observable: five pre-fills at their real 255 caps in astral text
        build a 15371-character URL that this loop cuts every one of. They are
        oversized so that the whole overrun turns on ONE comparison between
        TWO values that the two metrics order oppositely, which is the thing
        being pinned; at 255 apiece it would take five values to go over
        budget and the outcome would no longer isolate the metric.
        """
        with app.test_request_context():
            url = _bounded_scan_url('main.product_add',
                                    description='A ' * 1500,
                                    manufacturer='Ж' * 1900)

        query = _query(url)
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)
        assert query['description'] == 'A ' * 1500
        assert 0 < len(query['manufacturer']) < 1900

    def test_the_safe_set_is_the_one_url_for_actually_uses(self, app):
        """`_URL_QUERY_SAFE` is a copy of a set werkzeug owns, so something has
        to notice if the two ever diverge.

        The test above pins the CONSEQUENCE of the cost model — which value the
        loop reaches for — and would keep passing under a safe set that is
        merely close enough to keep that one ordering. This pins the model
        itself, against the only authority that matters: the characters
        `url_for` emits. It does that without naming
        `werkzeug.urls._urlencode`, whose leading underscore says it may be
        renamed; the probe is every printable ASCII character plus one
        representative of each UTF-8 width, and the predicted cost is compared
        against the emitted one character for character. A werkzeug upgrade
        that changes the encoding turns this red instead of silently making
        the ranking approximate.

        The probe is spelled out rather than built from `_URL_QUERY_SAFE`,
        which would make the test circular: a character REMOVED from the
        constant would leave the probe at the same moment, and the one
        disagreement it caused would go unmeasured.
        """
        probe = (''.join(chr(code) for code in range(0x20, 0x7f))
                 + 'ÉЖ漢\U0001f600')
        with app.test_request_context():
            emitted = url_for('main.product_add',
                              description=probe).split('description=', 1)[1]

        assert emitted == quote_plus(probe, safe=_URL_QUERY_SAFE)

    def test_a_path_argument_is_never_a_shrink_candidate(self, app):
        """`product_detail`'s `product_id` is an int in the PATH: slicing it
        would build a URL for a different product, or for none at all."""
        with app.test_request_context():
            url = _bounded_scan_url('main.product_detail', product_id=4242,
                                    description='\U0001f600' * 1000)

        assert _path(url) == '/products/4242'
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)

    @pytest.mark.parametrize('endpoint,args', [
        ('main.product_search', {'q': '\U0001f600' * _SCAN_URL_Q_LIMIT}),
        ('main.product_search', {'q': 'A' * _SCAN_URL_Q_LIMIT,
                                 'description': 'A' * 255}),
        ('main.product_search', {'q': '\U0001f600' * _SCAN_URL_Q_LIMIT,
                                 'description': '\U0001f600' * 255,
                                 'manufacturer': '\U0001f600' * 255,
                                 'category_path': '\U0001f600' * 512}),
        ('main.product_search', {'q': ''}),
        ('main.product_add', {}),
        ('main.product_add', {'description': '\U0001f600' * 255,
                              'category_path': '\U0001f600' * 512}),
        ('main.product_detail', {'product_id': 7,
                                 'scan_value': '\U0001f600' * 255}),
    ], ids=['q_only', 'ascii', 'everything', 'empty_q', 'bare_create',
            'create_prefills', 'detail'])
    def test_every_shape_terminates_with_an_in_app_path(self, app, endpoint,
                                                        args):
        """Both loops strictly decrease a non-negative integer each iteration,
        so neither can spin; and when there is nothing left to shrink the URL is
        returned as it stands rather than emptied. A long URL is a bad outcome,
        a dead end is a forbidden one (FR36/FR40)."""
        with app.test_request_context():
            url = _bounded_scan_url(endpoint, **args)

        assert url.startswith('/')
        assert len(url) <= _MAX_SCAN_URL_CHARS, len(url)


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
