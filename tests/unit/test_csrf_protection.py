"""
CSRF protection for the server-rendered forms.

Both `TestConfig`s set `WTF_CSRF_ENABLED = False` (config.py, tests/test_config.py)
for unit *and* e2e runs, so the whole suite stays green if a template's
`csrf_token` hidden input is deleted or misspelled, or if a form endpoint loses
server-side enforcement — while every real browser POST 400s.

Two halves are needed, and neither substitutes for the other:

  * the template scan proves the hidden input still exists in every POST form,
    but says nothing about enforcement;
  * the tokenless POSTs prove the server enforces CSRF, but pass just fine with
    the hidden input deleted.

The CSRF-enabled app follows the precedent at
tests/unit/test_scan_routes.py:336 and tests/unit/test_request_limits.py:1546 —
a `TestConfig` subclass with protection genuinely on, plus a control route that
must be rejected before any other assertion here is trusted.
"""

import logging
import re
from pathlib import Path

import pytest
from flask import session, url_for
from flask_wtf.csrf import CSRFError, generate_csrf

import app as app_package
from app import create_app, csrf
from config import TestConfig

TEMPLATE_ROOT = Path(app_package.__file__).parent / 'templates'

# Jinja templates are all `.html` today; scanning by suffix set rather than by
# `*.html` keeps a form moved into a `.jinja`/`.j2` partial from escaping.
TEMPLATE_SUFFIXES = {'.html', '.htm', '.jinja', '.j2'}

# Every `<form ...>` opening tag; `[^>]` spans newlines, so multi-line tags
# (product/detail.html) are matched whole.
_FORM_TAG = re.compile(r'<form\b[^>]*>', re.IGNORECASE)

# `method=...` on the form tag itself. The negative lookbehind keeps
# `data-method="post"`-style attributes from being mistaken for it. The value is
# captured whole (quotes included) so a Jinja-computed method is distinguishable
# from a literal one.
_METHOD_ATTR = re.compile(
    r'(?<![-\w])method\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)

# A hidden input named csrf_token whose value is rendered from Jinja's
# `csrf_token()`. Attribute order is not assumed.
_CSRF_INPUT = re.compile(
    r'<input\b'
    r'(?=[^>]*(?<![-\w])type\s*=\s*["\']hidden["\'])'
    r'(?=[^>]*(?<![-\w])name\s*=\s*["\']csrf_token["\'])'
    r'[^>]*(?<![-\w])value\s*=\s*["\']\s*\{\{\s*csrf_token\(\)\s*\}\}\s*["\']',
    re.IGNORECASE)


def _post_form_bodies(html):
    """Yield the body of every POST `<form>` in a template's source."""
    for tag in _FORM_TAG.finditer(html):
        method = _METHOD_ATTR.search(tag.group(0))
        if method is None:
            # No method attribute means GET, which needs no token.
            continue

        value = method.group(1).strip('"\'').strip()
        # A method computed by Jinja (`method="{{ ... }}"`) counts as POST: the
        # scan cannot prove it is a GET, and guessing GET would silently drop
        # the form from coverage.
        if value.upper() != 'POST' and '{{' not in value:
            continue

        # Case-insensitively, to match `_FORM_TAG` and the nested-form check
        # below: a `</FORM>` would otherwise read as an unclosed tag.
        closing = re.compile(r'</form\s*>', re.IGNORECASE).search(html, tag.end())
        end = -1 if closing is None else closing.start()
        assert end != -1, (
            'unclosed <form> tag; the scan would otherwise read to end-of-file '
            "and borrow another form's csrf_token")

        body = html[tag.end():end]
        assert '<form' not in body.lower(), (
            'nested or unclosed <form> tag; the inner form\'s csrf_token would '
            'be credited to the outer one')
        yield body


def _post_forms_missing_csrf(html):
    """Indexes (1-based) of the POST forms in `html` with no csrf_token input."""
    return [index
            for index, body in enumerate(_post_form_bodies(html), start=1)
            if _CSRF_INPUT.search(body) is None]


def _template_files():
    """Every Jinja template under `app/templates/**`, in a stable order."""
    return sorted(path for path in TEMPLATE_ROOT.rglob('*')
                  if path.is_file() and path.suffix.lower() in TEMPLATE_SUFFIXES)


def _post_form_counts():
    """{template path: number of POST forms}, derived at runtime.

    Derived from `app/templates/**` rather than hardcoded, so a newly added POST
    form -- including a second one in an already-listed template -- shows up
    here and fails the parity check until it is given endpoint coverage below.
    """
    counts = {}
    for path in _template_files():
        found = sum(1 for _ in _post_form_bodies(path.read_text(encoding='utf-8')))
        if found:
            counts[path.relative_to(TEMPLATE_ROOT).as_posix()] = found
    return counts


# (template, endpoint, url kwargs) for every POST form template. The endpoint is
# named rather than hardcoded as a path so a route rename fails loudly here
# instead of silently dropping coverage. The ids/args need not exist: CSRF is
# enforced in a before_request hook, so rejection happens before the view runs.
FORM_TEMPLATE_ENDPOINTS = [
    ('inventory/add.html', 'main.inventory_add', {}),
    ('inventory/edit.html', 'main.inventory_edit', {'ja_id': 'JA000001'}),
    ('inventory/move.html', 'main.inventory_move', {}),
    ('inventory/shorten.html', 'main.inventory_shorten', {}),
    ('product/add.html', 'main.product_add', {}),
    ('product/edit.html', 'main.product_edit', {'product_id': 1}),
    ('product/purchase_add.html', 'main.purchase_add', {'product_id': 1}),
    ('product/category_rename.html', 'main.category_rename', {}),
    ('product/detail.html', 'main.product_upload_attachment', {'product_id': 1}),
    ('admin/add_material.html', 'admin.add_material', {}),
]

# CSRF-protected POST endpoints driven by `fetch` with an `X-CSRFToken` header
# instead of a native form, so the scan above cannot see them. Enforcement is
# the same before_request hook, and these are equally able to lose it.
JS_POST_ENDPOINTS = [
    ('admin.update_material_status', {}),
    ('admin.validate_material', {}),
]

# The `@csrf.exempt` surface, pinned. It is larger than the protected surface,
# and an exemption is the one way an endpoint can leave CSRF enforcement
# without failing anything above: the coverage parity check below derives the
# protected set from the url_map, so an endpoint that becomes exempt simply
# disappears from it. Adding or removing an entry here is meant to be a
# deliberate edit accompanying a deliberate decision.
EXEMPT_VIEWS = {
    'app.main.routes.api_admin_export',
    'app.main.routes.api_advanced_search',
    'app.main.routes.api_create_items',
    'app.main.routes.api_export_validate',
    'app.main.routes.api_record_purchase',
    'app.main.routes.api_scan',
    'app.main.routes.api_toggle_item_status',
    'app.main.routes.batch_move_items',
    'app.main.routes.cleanup_orphaned_photos',
    'app.main.routes.copy_photos',
    'app.main.routes.delete_photo',
    'app.main.routes.duplicate_item',
    'app.main.routes.print_label',
    'app.main.routes.regenerate_pdf_thumbnails',
    'app.main.routes.upload_photo',
    'app.main.routes.validate_type_shape',
}

# Proof that the rejection came from CSRF and not from a view answering 400 for
# its own reasons (`main.inventory_add` does exactly that on an empty body).
# A dedicated handler is asserted on rather than Flask-WTF's English prose, so a
# dependency bump rewording "The CSRF token is missing." cannot turn this file
# red for a non-defect.
CSRF_SENTINEL = b'__csrf_rejected__'


def _csrf_app(test_storage):
    """An app with CSRF protection genuinely switched on."""
    class CsrfEnabledConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfEnabledConfig, storage_backend=test_storage)

    @app.route('/__csrf_control__', methods=['POST'])
    def _csrf_control():
        return 'reached'

    @app.errorhandler(CSRFError)
    def _csrf_rejected(error):
        # The reason rides along in a header so a test can assert that two
        # rejections have *different* causes without hardcoding Flask-WTF's
        # English prose, which a dependency bump is free to reword.
        return CSRF_SENTINEL, 400, {'X-CSRF-Reason': error.description}

    return app


# Every logger `setup_logging` reconfigures on each `create_app`. The empty
# string is the root logger, whose handlers it *replaces* outright (pytest's
# own capture handler included) and whose level it rewrites from the config's
# LOG_LEVEL. `''` and `'app'` are as much a part of the blast radius as the
# five specialized loggers.
_SHARED_LOGGERS = ('', 'app', 'performance', 'api_access', 'google_sheets',
                   'inventory', 'mariadb_catalog_service')


@pytest.fixture
def csrf_app(test_storage):
    """A CSRF-enabled app whose construction does not leak logging state.

    `create_app` -> `setup_logging` calls `addHandler` on module-level loggers
    without ever clearing them, and `setLevel`s them (plus the root logger) to
    the config's LOG_LEVEL. Each app built therefore leaves one more handler on
    the shared `inventory` logger and its siblings, and drags the root logger
    from WARNING down to INFO. This file builds one app per test case (~40 of
    them), which would otherwise leave every later test that reads log output
    -- `tests/unit/test_audit_redaction.py` among them -- reading duplicated
    records at an unexpected level.

    Handlers AND levels are restored: restoring only the handler lists leaves
    the levels behind, which is the half the first version of this fixture
    missed.
    """
    saved = {name: (logging.getLogger(name).handlers[:],
                    logging.getLogger(name).level)
             for name in _SHARED_LOGGERS}
    try:
        yield _csrf_app(test_storage)
    finally:
        for name, (handlers, level) in saved.items():
            logger = logging.getLogger(name)
            logger.handlers = handlers
            logger.setLevel(level)


def _csrf_protected_endpoints(app):
    """The endpoints this app actually enforces CSRF on, from the url_map.

    Derived rather than listed, so an endpoint that gains CSRF enforcement --
    a new form route, a new `fetch` handler, an exemption removed -- shows up
    here and fails the parity check until it is given coverage below.

    Enforced methods come from `WTF_CSRF_METHODS`, not a hardcoded `POST`: the
    default set is {POST, PUT, PATCH, DELETE}, and the app already routes a
    `PATCH /api/inventory/<ja_id>/status` and a `DELETE /api/photos/<id>`
    (both exempt today). A protected PUT/PATCH/DELETE added tomorrow would
    otherwise be invisible here AND to the template scan, with nothing to
    notice it.
    """
    enforced_methods = set(app.config['WTF_CSRF_METHODS'])
    endpoints = set()
    for rule in app.url_map.iter_rules():
        if not (rule.methods or set()) & enforced_methods:
            continue
        view = app.view_functions[rule.endpoint]
        if f'{view.__module__}.{view.__name__}' in csrf._exempt_views:
            continue
        endpoints.add(rule.endpoint)
    # The control route this file adds is not part of the app's real surface.
    endpoints.discard('_csrf_control')
    return endpoints


def _mint_valid_token(app, client):
    """A `csrf_token` value the app will accept, with the matching session."""
    with app.test_request_context():
        token = generate_csrf()
        raw = session['csrf_token']

    with client.session_transaction() as client_session:
        client_session['csrf_token'] = raw

    return token


def _seed_session_only(app, client):
    """Give the client a valid CSRF session WITHOUT handing it the token.

    A forged-token POST from a client with no session at all never reaches
    Flask-WTF's token comparison -- it short-circuits on "The CSRF session
    token is missing.", so it proves nothing about whether a WRONG token is
    actually rejected. Seeding the session is what pushes the request past that
    early return and into the signature check.
    """
    with app.test_request_context():
        generate_csrf()
        raw = session['csrf_token']

    with client.session_transaction() as client_session:
        client_session['csrf_token'] = raw


@pytest.mark.unit
class TestPostFormTemplatesCarryACsrfToken:
    """Static half: the hidden input is still in the markup."""

    def test_every_post_form_template_renders_a_csrf_token_input(self):
        offenders = []
        for path in _template_files():
            html = path.read_text(encoding='utf-8')
            for index in _post_forms_missing_csrf(html):
                offenders.append(
                    f'{path.relative_to(TEMPLATE_ROOT).as_posix()} (form #{index})')

        assert not offenders, (
            'POST form(s) with no <input type="hidden" name="csrf_token" '
            'value="{{ csrf_token() }}">: ' + ', '.join(offenders))

    def test_the_scan_actually_finds_the_known_post_forms(self):
        """Without this, a scanner that matched nothing would pass vacuously.

        Counted per form, not per template: a second POST form added to an
        already-listed template must fail here until it gets endpoint coverage.
        """
        covered = {}
        for template, _, _ in FORM_TEMPLATE_ENDPOINTS:
            covered[template] = covered.get(template, 0) + 1

        assert _post_form_counts() == covered

    def test_a_template_missing_its_token_is_reported(self):
        """The failure mode the scan exists for: a deleted or misspelled input."""
        deleted = '<form method="POST"><input name="ja_id"></form>'
        misspelled = ('<form method="POST">'
                      '<input type="hidden" name="csrf-token" '
                      'value="{{ csrf_token() }}"></form>')
        static_value = ('<form method="POST">'
                        '<input type="hidden" name="csrf_token" value="abc">'
                        '</form>')

        assert _post_forms_missing_csrf(deleted) == [1]
        assert _post_forms_missing_csrf(misspelled) == [1]
        assert _post_forms_missing_csrf(static_value) == [1]

    def test_a_jinja_computed_method_is_treated_as_a_post_form(self):
        """The scan cannot prove `method="{{ verb }}"` is a GET, and assuming
        GET would drop the form from coverage silently."""
        assert _post_forms_missing_csrf(
            '<form method="{{ verb }}"><input name="ja_id"></form>') == [1]

    def test_a_malformed_form_fails_loudly_instead_of_borrowing_a_token(self):
        """Both shapes would otherwise credit one form's token to another."""
        unclosed = ('<form method="POST"><input name="ja_id">'
                    '<div>no closing tag</div>')
        nested = ('<form method="POST"><input name="ja_id">'
                  '<form method="POST"><input type="hidden" name="csrf_token" '
                  'value="{{ csrf_token() }}"></form></form>')

        with pytest.raises(AssertionError):
            _post_forms_missing_csrf(unclosed)
        with pytest.raises(AssertionError):
            _post_forms_missing_csrf(nested)

    def test_get_forms_are_not_required_to_carry_a_token(self):
        """GET forms — explicit or by omission — are outside CSRF's scope."""
        assert _post_forms_missing_csrf('<form method="GET"></form>') == []
        assert _post_forms_missing_csrf('<form id="advanced-search"></form>') == []

    def test_a_well_formed_post_form_passes(self):
        """The positive control for the checker itself."""
        html = ('<form method="POST" novalidate>'
                '<input type="hidden" name="csrf_token" '
                'value="{{ csrf_token() }}"/></form>')
        assert _post_forms_missing_csrf(html) == []


@pytest.mark.unit
class TestEveryProtectedEndpointIsCovered:
    """The scan proves the *templates* are complete; this proves the *endpoint
    list* is.

    Without it the two lists below are hand-maintained, and the gap is silent
    in both directions: a new `fetch`-driven POST endpoint gets no coverage at
    all, and a form whose `<form>` tag carries no `method` -- `export-form`
    (`admin/export.html`) and `advanced-search-form` (`inventory/search.html`)
    are both submitted by a JS `fetch(..., method: 'POST')` -- is invisible to
    the template scan too. Both are covered today only by their endpoints being
    `@csrf.exempt`; deriving the protected set from the url_map is what notices
    when that stops being true.
    """

    def test_every_csrf_protected_post_endpoint_has_coverage(self, csrf_app):
        covered = ({endpoint for _, endpoint, _ in FORM_TEMPLATE_ENDPOINTS}
                   | {endpoint for endpoint, _ in JS_POST_ENDPOINTS})

        assert _csrf_protected_endpoints(csrf_app) == covered, (
            'the set of CSRF-enforcing POST endpoints no longer matches the '
            'endpoints tested below; add the new endpoint to '
            'FORM_TEMPLATE_ENDPOINTS or JS_POST_ENDPOINTS')

    def test_the_exempt_surface_has_not_drifted(self, csrf_app):
        """An added `@csrf.exempt` silently shrinks the protected set the check
        above derives, so it would take an endpoint out of coverage without
        failing anything. Removing protection should require saying so here."""
        assert csrf._exempt_views == EXEMPT_VIEWS, (
            'the @csrf.exempt set changed; each of these endpoints accepts '
            'cross-site POSTs, so update EXEMPT_VIEWS deliberately')


@pytest.mark.unit
class TestFormEndpointsRejectTokenlessPosts:
    """Behavioural half: the server enforces what the templates send."""

    def test_csrf_protection_is_genuinely_on_in_this_app(self, csrf_app):
        """Control. Without it, every assertion below could pass vacuously."""
        resp = csrf_app.test_client().post('/__csrf_control__')
        assert resp.status_code == 400
        assert resp.data == CSRF_SENTINEL

    def test_a_valid_token_is_accepted(self, csrf_app):
        """The other half of the control, and the failure this file would
        otherwise be blind to: an app that rejected *every* POST -- broken
        `csrf_token()` generation, a bad SECRET_KEY, an over-broad hook --
        passes every rejection assertion here while no real form works."""
        app = csrf_app
        client = app.test_client()

        resp = client.post('/__csrf_control__',
                           data={'csrf_token': _mint_valid_token(app, client)})

        assert resp.data == b'reached'
        assert resp.status_code == 200

    @pytest.mark.parametrize('template,endpoint,url_args', FORM_TEMPLATE_ENDPOINTS,
                             ids=[t for t, _, _ in FORM_TEMPLATE_ENDPOINTS])
    def test_form_endpoint_rejects_a_post_without_a_token(
            self, csrf_app, template, endpoint, url_args):
        app = csrf_app
        client = app.test_client()

        # Re-asserted per case rather than relied upon from the control test:
        # a parametrized case that ran against an unprotected app would pass
        # for the wrong reason.
        assert client.post('/__csrf_control__').data == CSRF_SENTINEL, (
            'CSRF protection is not on; the assertion below would be vacuous')

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        resp = client.post(url, data={'description': 'no token here'})
        # The status alone is not proof: `main.inventory_add` answers this same
        # body with 400 for its own missing-required-fields reason even when
        # CSRF is off. Pinning the rejection *reason* keeps that case honest.
        assert resp.data == CSRF_SENTINEL, (
            f'{endpoint} ({template}) did not reject a tokenless POST as a '
            f'CSRF failure: {resp.status_code} {resp.data[:200]!r}')

    @pytest.mark.parametrize('template,endpoint,url_args', FORM_TEMPLATE_ENDPOINTS,
                             ids=[t for t, _, _ in FORM_TEMPLATE_ENDPOINTS])
    def test_form_endpoint_rejects_a_forged_token(
            self, csrf_app, template, endpoint, url_args):
        """Enforcement that accepted any non-empty value would satisfy every
        tokenless case above.

        The session is seeded deliberately. Without it Flask-WTF returns on
        "The CSRF session token is missing." before it ever compares the
        submitted value, so the forgery would be rejected for the same reason
        the tokenless case already covers and the signature check -- the part
        that actually stops a forged token -- would be exercised by nothing in
        this file.
        """
        app = csrf_app
        client = app.test_client()

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        # The same forged POST from a client with NO CSRF session. Flask-WTF
        # short-circuits that one before it ever compares the token, so its
        # rejection reason is the baseline this case must NOT match.
        short_circuited = app.test_client().post(
            url, data={'csrf_token': 'forged-not-a-real-token',
                       'description': 'bad token'})

        _seed_session_only(app, client)

        resp = client.post(url, data={'csrf_token': 'forged-not-a-real-token',
                                      'description': 'bad token'})
        assert resp.data == CSRF_SENTINEL, (
            f'{endpoint} ({template}) accepted a forged csrf_token: '
            f'{resp.status_code} {resp.data[:200]!r}')
        # ...and it was rejected by COMPARING the token, not by short-circuiting
        # on a missing CSRF session. Without the seeding above, this case would
        # silently degrade into a duplicate of the tokenless one and the
        # signature check would be exercised by nothing in this file.
        assert (resp.headers.get('X-CSRF-Reason')
                != short_circuited.headers.get('X-CSRF-Reason')), (
            f'{endpoint} ({template}) rejected the forged token for the same '
            'reason a sessionless client gets, so the token comparison itself '
            f'is untested: {resp.headers.get("X-CSRF-Reason")!r}')

    @pytest.mark.parametrize('template,endpoint,url_args', FORM_TEMPLATE_ENDPOINTS,
                             ids=[t for t, _, _ in FORM_TEMPLATE_ENDPOINTS])
    def test_form_endpoint_lets_a_valid_token_through_the_gate(
            self, csrf_app, template, endpoint, url_args):
        """Per endpoint, not just on the control route: whatever the view then
        does with an incomplete body, the CSRF gate must not be what stopped
        it. Without this, blanket rejection reads as perfect enforcement."""
        app = csrf_app
        client = app.test_client()

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        resp = client.post(url, data={'csrf_token': _mint_valid_token(app, client),
                                      'description': 'has a valid token'})
        assert resp.data != CSRF_SENTINEL, (
            f'{endpoint} ({template}) rejected a VALID csrf_token')
        # "Not a CSRF rejection" is not the same as "the gate opened": a route
        # that failed on its own terms is also not the sentinel. Under
        # `TESTING` an unhandled exception propagates out of `client.post`
        # rather than becoming a 500, so that shape already fails loudly above;
        # this catches the case where something downstream *converts* a crash
        # into a 500 response instead.
        assert resp.status_code != 500, (
            f'{endpoint} ({template}) raised past the CSRF gate; this case can '
            f'no longer tell an open gate from a crash: {resp.data[:200]!r}')

    @pytest.mark.parametrize('endpoint,url_args', JS_POST_ENDPOINTS,
                             ids=[e for e, _ in JS_POST_ENDPOINTS])
    def test_js_driven_endpoint_rejects_a_post_without_a_token(
            self, csrf_app, endpoint, url_args):
        """These POST via `fetch` with an `X-CSRFToken` header, so the template
        scan cannot see them, but they are not exempt and must still enforce."""
        app = csrf_app
        client = app.test_client()

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        assert client.post(url, json={'status': 'active'}).data == CSRF_SENTINEL, (
            f'{endpoint} accepted a POST with no CSRF token')

    @pytest.mark.parametrize('endpoint,url_args', JS_POST_ENDPOINTS,
                             ids=[e for e, _ in JS_POST_ENDPOINTS])
    def test_js_driven_endpoint_accepts_a_valid_x_csrftoken_header(
            self, csrf_app, endpoint, url_args):
        """The positive control for the *header* channel.

        These two endpoints receive their token in an `X-CSRFToken` header
        (admin/materials_overview.html, admin/add_material.html), not in the
        form body -- a different Flask-WTF code path, driven by
        `WTF_CSRF_HEADERS`. Rejection-only coverage would stay green if that
        channel broke, while every admin JS POST 400s in a real browser: the
        same blind spot `..._lets_a_valid_token_through_the_gate` exists to
        close for the form endpoints.
        """
        app = csrf_app
        client = app.test_client()

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        resp = client.post(url, json={'status': 'active'},
                           headers={'X-CSRFToken': _mint_valid_token(app, client)})

        assert resp.data != CSRF_SENTINEL, (
            f'{endpoint} rejected a valid token supplied via X-CSRFToken; the '
            'header channel every admin fetch() uses is broken')
        assert resp.status_code != 500, (
            f'{endpoint} returned 500 past the CSRF gate; this case can no '
            f'longer tell an open gate from a crash: {resp.data[:200]!r}')

    @pytest.mark.parametrize('endpoint,url_args', JS_POST_ENDPOINTS,
                             ids=[e for e, _ in JS_POST_ENDPOINTS])
    def test_js_driven_endpoint_rejects_a_forged_x_csrftoken_header(
            self, csrf_app, endpoint, url_args):
        """...and the header channel must not accept just any value either."""
        app = csrf_app
        client = app.test_client()

        with app.test_request_context():
            url = url_for(endpoint, **url_args)

        short_circuited = app.test_client().post(
            url, json={'status': 'active'}, headers={'X-CSRFToken': 'forged'})

        _seed_session_only(app, client)

        resp = client.post(url, json={'status': 'active'},
                           headers={'X-CSRFToken': 'forged'})
        assert resp.data == CSRF_SENTINEL, (
            f'{endpoint} accepted a forged X-CSRFToken header')
        assert (resp.headers.get('X-CSRF-Reason')
                != short_circuited.headers.get('X-CSRF-Reason')), (
            f'{endpoint} rejected the forged header token for the same reason a '
            'sessionless client gets; the header token is never compared')


@pytest.mark.unit
class TestCsrfStaysEnabledOutsideTheTestConfigs:
    """The premise of this whole file is that a config flag blinded the suite.

    Every app built here forces `WTF_CSRF_ENABLED = True` in its own subclass,
    so nothing above would notice if the flag were switched off for the app
    that actually ships. `config.Config` relies on Flask-WTF's default (`True`)
    and never sets it; this is the guard that makes turning it off deliberate.
    """

    def test_the_base_config_does_not_disable_csrf(self):
        from config import Config

        assert getattr(Config, 'WTF_CSRF_ENABLED', True) is True, (
            'config.Config disables CSRF, so every deployed form endpoint '
            'accepts cross-site POSTs')

    def test_the_production_config_does_not_disable_csrf(self):
        import config as config_module

        offenders = [
            name for name in dir(config_module)
            if isinstance(getattr(config_module, name), type)
            and issubclass(getattr(config_module, name), config_module.Config)
            and 'test' not in name.lower()
            and getattr(getattr(config_module, name),
                        'WTF_CSRF_ENABLED', True) is not True
        ]
        assert not offenders, (
            f'non-test config(s) disable CSRF protection: {offenders}')
