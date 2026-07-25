"""
Route tests for the wedge-scan capture endpoint, POST /api/scan (Story 4.1, FR35).

Uses the `client` fixture. The endpoint touches no database and constructs no
service, so no storage fixture is needed anywhere in this module — that is
itself part of the contract: resolution is Story 4.3's.
"""

import pytest

from app.main.routes import MAX_SCAN_LENGTH, _clean_scan_input


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

    def test_happy_path_echoes_raw_unrouted(self, client):
        """A plain GTIN posts and comes back verbatim, marked unrouted."""
        resp = client.post('/api/scan', json={'raw': '00012345678905'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['raw'] == '00012345678905'
        assert data['outcome'] == 'unrouted'

    @pytest.mark.parametrize('raw, expected', [
        ('  0123 \r\n', '0123'),                     # outer whitespace stripped
        ('[)>\x1e06\x1dP123\x1e\x04', '[)>\x1e06\x1dP123\x1e\x04'),  # control chars survive
        ('a b\tc', 'a b\tc'),                        # interior whitespace kept
        ('96WITabc', '96WITabc'),                    # case preserved, never uppercased
        ('96WITABC1234567', '96WITABC1234567'),      # internal GS1 AI-96 payload
        ('  [)>\x1e06\x1dP123\x1e\x04  ', '[)>\x1e06\x1dP123\x1e\x04'),  # trim outside, keep inside
    ])
    def test_raw_is_echoed_byte_for_byte(self, client, raw, expected):
        """FR35: verbatim apart from outer space/tab/CR/LF."""
        resp = client.post('/api/scan', json={'raw': raw})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['raw'] == expected
        assert data['outcome'] == 'unrouted'

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

    def test_endpoint_constructs_no_catalog_service(self, client, monkeypatch):
        """The story's stated contract: no service, no database.

        Asserted rather than merely described, so wiring `_get_catalog_service`
        in during Story 4.2/4.3 is a deliberate act that turns a test red
        instead of a comment quietly going stale.
        """
        calls = []
        monkeypatch.setattr(
            'app.main.routes._get_catalog_service',
            lambda *args, **kwargs: calls.append(True))

        assert client.post('/api/scan', json={'raw': '0123'}).status_code == 200
        assert calls == []

    def test_response_has_no_resolution_fields(self, client):
        """Story 4.1 resolves nothing; 4.2/4.3 add to this shape, not this story."""
        data = client.post('/api/scan', json={'raw': '0123'}).get_json()
        assert set(data.keys()) == {'success', 'raw', 'outcome'}
