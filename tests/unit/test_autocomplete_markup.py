"""
Markup tripwire for the shared autocomplete dropdown containers.

The sixteen `#<field>-suggestions` divs across the item and product forms used
to carry an identical `style="max-height: 200px; overflow-y: auto;
z-index: 1000;"` attribute, copy-pasted each time a field was wired up. That is
now one `.suggestions-menu` rule in `app/static/css/main.css`.

Nothing at runtime notices if a seventeenth field arrives with the old
copy-pasted style instead of the class — it would look right and only be
inconsistent, which is exactly the kind of drift that never gets caught. So the
templates are scanned as text here: the inline style must be gone everywhere,
every suggestion div must carry the class, and the class must actually define
the three declarations it replaced.

Scanned as text rather than parsed: the files are Jinja templates, and an HTML
parser would either choke on the `{% ... %}` tags or need them stripped first,
which is more machinery than a class-list check deserves.

The same idiom, applied to the component's own source, is what pins the one
number `field-autocomplete.js` is forced to duplicate from the server
(`MAX_QUERY_CHARS`, DW-95). There is no build step and no module system on that
side, so the browser cannot import `SEARCH_QUERY_MAX_LENGTH`; nothing at
runtime notices if the two drift, because a browser bound that disagrees with
the server's still produces a working dropdown that merely answers a different
question. Reading the literal out of the source is the only place the two can
be compared at all.
"""

import re
from pathlib import Path

import pytest

from app.main.routes import _MAX_SCAN_URL_CHARS
from app.utils.sql_text import SEARCH_QUERY_MAX_LENGTH

APP_ROOT = Path(__file__).resolve().parents[2] / 'app'
TEMPLATE_ROOT = APP_ROOT / 'templates'
MAIN_CSS = APP_ROOT / 'static' / 'css' / 'main.css'
FIELD_AUTOCOMPLETE_JS = APP_ROOT / 'static' / 'js' / 'field-autocomplete.js'

#: The attribute this change deleted, in the exact form all sixteen carried.
LEGACY_INLINE_STYLE = 'max-height: 200px; overflow-y: auto; z-index: 1000'

#: Any div whose id follows the `<field>-suggestions` convention the component
#: attaches by. `[^>]` already spans newlines, which matters because the
#: attributes are wrapped across lines in several of the templates. Either
#: quote style is accepted: a div added with single quotes would otherwise slip
#: past the very drift this module exists to catch — and so would a hyphenated
#: id, which is why the id charset allows `-` as well as `_`. Every field wired
#: today is underscore-named, but this pattern is the whole tripwire: an id it
#: cannot match is a dropdown none of the assertions below ever see.
SUGGESTION_DIV = re.compile(
    r'''<div\b[^>]*\bid=["'](?P<id>[A-Za-z0-9_][A-Za-z0-9_-]*-suggestions)["'][^>]*>''')


def _css_without_comments():
    """`main.css` with its `/* ... */` comments stripped.

    The comments in this stylesheet name the very selectors these tests search
    for — the `.suggestions-menu` rule's own comment explains why it is not
    `.autocomplete-dropdown` — so a raw text search finds the prose, not the
    CSS."""
    return re.sub(r'/\*.*?\*/', '', MAIN_CSS.read_text(encoding='utf-8'),
                  flags=re.DOTALL)


def _rule(css, selector):
    # Bounded on the right by `(?![\w-])` so looking up `.suggestions-menu`
    # cannot silently return a future `.suggestions-menu-wide` rule and report
    # on the wrong one. Nothing guards the left, deliberately: the selector
    # begins with `.`, which is already a boundary — `.foo-suggestions-menu`
    # does not contain the substring `.suggestions-menu` — and a lookbehind
    # here would reject the legitimate compound form `.dropdown-menu.suggestions-menu`.
    match = re.search(
        r'(?P<selector>[^{}]*?%s(?![\w-])[^{}]*?)\{(?P<body>[^}]*)\}'
        % re.escape(selector), css)
    assert match is not None, f'main.css does not define {selector}'
    return match


def _rule_selector(css, selector):
    """The full selector list of the rule defining `selector` — which is what
    reveals a rule that was merged into another one."""
    return _rule(css, selector).group('selector')


def _rule_body(css, selector):
    return _rule(css, selector).group('body')


def _templates():
    return sorted(TEMPLATE_ROOT.rglob('*.html'))


def _suggestion_divs():
    """Every `(template path, id, full opening tag)` in `app/templates`."""
    found = []
    for path in _templates():
        body = path.read_text(encoding='utf-8')
        for match in SUGGESTION_DIV.finditer(body):
            found.append((path, match.group('id'), match.group(0)))
    return found


@pytest.mark.unit
class TestSuggestionDivMarkup:

    def test_the_templates_are_actually_being_scanned(self):
        """A guard on the guard: a glob that silently matched nothing would
        make every assertion below vacuously true."""
        divs = _suggestion_divs()
        assert len(divs) >= 16, (
            f'expected the full set of suggestion divs, found {len(divs)}')

    def test_no_suggestion_div_carries_the_old_inline_style(self):
        """Scoped to the suggestion divs, not to whole template files: the
        same three declarations are a perfectly reasonable inline style on
        some unrelated scrollable overlay, and telling its author to reach for
        `suggestions-menu` would be wrong advice."""
        offenders = [f'{path.relative_to(TEMPLATE_ROOT)}#{div_id}'
                     for path, div_id, tag in _suggestion_divs()
                     if LEGACY_INLINE_STYLE in tag]
        assert offenders == [], (
            'these suggestion dropdowns still inline the geometry instead of '
            f'using class="suggestions-menu": {offenders}')

    def test_every_suggestion_div_carries_the_shared_class(self):
        offenders = [f'{path.relative_to(TEMPLATE_ROOT)}#{div_id}'
                     for path, div_id, tag in _suggestion_divs()
                     if 'suggestions-menu' not in tag]
        assert offenders == [], (
            'these suggestion dropdowns are missing the suggestions-menu '
            f'class: {offenders}')

    def test_no_suggestion_div_carries_a_style_attribute_at_all(self):
        """Broader than the exact-string check above, over the same set of
        divs: a NEW field copied from an older revision of one of these
        templates could arrive with the same declarations reordered or
        reformatted, which the literal search would miss."""
        offenders = [f'{path.relative_to(TEMPLATE_ROOT)}#{div_id}'
                     for path, div_id, tag in _suggestion_divs()
                     if 'style=' in tag]
        assert offenders == [], (
            f'these suggestion dropdowns still have inline styles: {offenders}')


@pytest.mark.unit
class TestSuggestionsMenuRule:

    def test_main_css_defines_the_class_with_all_three_declarations(self):
        """The class has to replace the inline style declaration for
        declaration: the change is required to be visually identical, and a
        rule that quietly dropped one would not fail anything else.

        `z-index` is pinned for parity, not because it is doing work on its
        own — Bootstrap's `.dropdown-menu`, which every one of these divs also
        carries, already sets `z-index: var(--bs-dropdown-zindex)` to the same
        1000. It stays so the class remains a faithful replacement for the
        attribute it replaced, and so the geometry does not depend on which
        other classes a future div happens to carry."""
        css = _css_without_comments()
        match = re.search(r'\.suggestions-menu\s*\{(?P<body>[^}]*)\}', css)
        assert match is not None, 'main.css does not define .suggestions-menu'
        body = match.group('body')
        for declaration in ('max-height: 200px',
                            'overflow-y: auto',
                            'z-index: 1000'):
            assert declaration in body, (
                f'.suggestions-menu is missing `{declaration}`')

    def test_the_rule_stands_apart_from_the_legacy_widget_rule(self):
        """`.autocomplete-dropdown` is the old main.js widget's rule, and
        carries `!important` background/border/shadow declarations that would
        fight the `.dropdown-menu` these divs also carry. Merging the two —
        the obvious "de-duplication" a later reader is tempted by — would
        silently restyle both widgets.

        The assertion is on the `!important`s rather than on the two rules'
        differing `max-height` values: the legacy widget overrides its own
        stylesheet with an inline `style.cssText` (`app/static/js/main.js`),
        so its declared cap is dead weight and pinning it here would fail the
        day someone tidies it away."""
        css = _css_without_comments()
        assert '.suggestions-menu' not in _rule_selector(css,
                                                         '.autocomplete-dropdown')
        assert '.autocomplete-dropdown' not in _rule_selector(
            css, '.suggestions-menu')
        # The reason they cannot merge, still true of the legacy rule.
        assert '!important' in _rule_body(css, '.autocomplete-dropdown')
        assert '!important' not in _rule_body(css, '.suggestions-menu')


#: The browser's copy of the server's query-length bound, as declared. Anchored
#: to `const` at the head of a line so a mention of the name in prose or in an
#: expression cannot be mistaken for the declaration. The leading `\s*` is
#: required rather than incidental — every declaration in that file is indented
#: inside its IIFE — so this deliberately cannot tell the module constant from
#: an equally-indented local of the same name, and `search` reads whichever
#: comes first. A second declaration of this name is a defect either way.
MAX_QUERY_CHARS_DECL = re.compile(
    r'^\s*const MAX_QUERY_CHARS\s*=\s*(?P<value>\d+);', re.MULTILINE)

#: The browser's copy of the transport bound, same anchoring, same reason.
MAX_URL_CHARS_DECL = re.compile(
    r'^\s*const MAX_URL_CHARS\s*=\s*(?P<value>\d+);', re.MULTILINE)

#: The whole refusal block, matched as ONE unit rather than as three
#: independent substring searches. Ordering and adjacency are the property
#: under test: `hide()` present SOMEWHERE in the method proves nothing, and a
#: block that hides and announces but forgets to `return` falls through to
#: `fetch(null)` — a `GET /null`, a 404, and a hide that reads as "no matches".
#: That is a refusal handled as a failure, which is exactly what this pins
#: shut, and no unordered `in` check can see it.
REFUSAL_BLOCK = re.compile(
    r'if \(url === null\) \{\s*'
    r'this\.hide\(\);\s*'
    r'this\.announce\(0, null\);\s*'
    r'return;\s*'
    r'\}')


def _js_without_comments(source):
    """`field-autocomplete.js` with its comments stripped, for the same reason
    `_css_without_comments` exists.

    The comments in this file argue ABOUT the identifiers these tests search
    for — the MAX_QUERY_CHARS block spells out what `console.warn` means here,
    and the refusal's own comment says why it must not use one — so a raw text
    search finds the prose instead of the code, and the "no warning on this
    path" assertion would fail on the sentence explaining that there is none.

    Only whole-line `//` comments are removed: that is how every comment in
    this file is written, and stripping trailing ones would need the string
    literals parsed to avoid eating a `//` inside one.
    """
    without_blocks = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    return re.sub(r'^[ \t]*//.*$', '', without_blocks, flags=re.MULTILINE)


def _js_slice(source, start, end):
    """The text of `source` from `start` up to the next `end` after it.

    Both markers are asserted rather than allowed to return -1, because a
    renamed method would otherwise silently reduce the assertions below to
    searches over an empty string — the vacuous-pass failure mode that
    `test_the_templates_are_actually_being_scanned` guards the other half of
    this module against.
    """
    begin = source.find(start)
    assert begin != -1, f'field-autocomplete.js no longer contains `{start}`'
    stop = source.find(end, begin)
    assert stop != -1, (
        f'field-autocomplete.js no longer has `{end}` after `{start}`')
    return source[begin:stop]


@pytest.mark.unit
class TestQueryLengthBoundTripwire:
    """The two numbers the component is forced to duplicate (DW-95, DW-162):
    the server's query bound and the transport's URL bound. Neither can be
    imported by a browser with no build step and no module system, and drift in
    either is SILENT — a dropdown that quietly stops appearing looks exactly
    like one that found nothing."""

    @pytest.fixture
    def source(self):
        return _js_without_comments(
            FIELD_AUTOCOMPLETE_JS.read_text(encoding='utf-8'))

    def test_the_browser_copy_equals_the_server_constant(self, source):
        """Compared against the IMPORTED constant, never a repeated literal:
        the failure this guards is precisely that one of the two numbers
        changed, and a third hardcoded copy in the test would be free to agree
        with whichever one it was written beside."""
        match = MAX_QUERY_CHARS_DECL.search(source)
        assert match is not None, (
            'field-autocomplete.js no longer declares MAX_QUERY_CHARS')
        assert int(match.group('value')) == SEARCH_QUERY_MAX_LENGTH, (
            'the browser and the server disagree about how long a suggestion '
            'query may be; they are one rule stated twice')

    def test_the_transport_bound_equals_the_scan_redirect_bound(self, source):
        """`MAX_URL_CHARS` and `_MAX_SCAN_URL_CHARS` are not two policies that
        happen to agree — they are one statement about one transport (gunicorn's
        request line, nginx's header buffer), made in the two places that build
        a URL from operator text. Whichever of the two a future reader measures
        against a real server, the other has to move with it."""
        match = MAX_URL_CHARS_DECL.search(source)
        assert match is not None, (
            'field-autocomplete.js no longer declares MAX_URL_CHARS')
        assert int(match.group('value')) == _MAX_SCAN_URL_CHARS, (
            'the autocomplete request and the scan redirect disagree about '
            'what this transport accepts')

    def test_build_url_bounds_the_finished_url_and_not_only_its_parts(
            self, source):
        """Three checks, because the per-value pair cannot do the transport's
        job alone and the finished-URL check cannot do the server's.

        `q` and `location` are each held to the SERVER's number so the browser
        does not ask a question the answer to which is already known to be
        `[]`. But percent-encoding expands one character to up to twelve bytes,
        and two values each individually under the cap still sum — `q` and
        `location` at 4096 apiece clear both per-value checks and emit 8259
        bytes, past gunicorn's 8190. Only the check on the assembled, already-
        encoded string bounds what actually goes on the wire, which is the
        defect (DW-162) this exists for. `_bounded_scan_url` reached the same
        conclusion for the same transport and writes down why."""
        build_url = _js_slice(source, '        buildUrl() {',
                              '        async fetchAndRender()')
        assert 'q.length > MAX_QUERY_CHARS) return null;' in build_url
        assert 'loc.length > MAX_QUERY_CHARS) return null;' in build_url
        assert 'url.length > MAX_URL_CHARS) return null;' in build_url
        # Measured AFTER `params.toString()`, or it measures the wrong string.
        assert build_url.index('const qs = params.toString();') < \
            build_url.index('url.length > MAX_URL_CHARS')

    def test_the_refusal_hides_announces_and_returns_without_warning(
            self, source):
        """Three properties of one block, pinned as one block (see
        REFUSAL_BLOCK for why the adjacency is the point).

        It must `hide()` AND `announce(0, null)`, which is render()'s
        no-matches pair: hide() clears the live region, so a bare hide() would
        answer a screen reader with silence where the server's own `[]` for the
        same input says "No suggestions" — the pasted-value operator is exactly
        the one most likely to reach this path. It must `return`, or it falls
        into `fetch(null)`. And it must sit ahead of the `try` that owns
        `console.warn`, this file's signal for an UNEXPECTED failure: a refusal
        whose answer is already known is an ordinary decision, and one handled
        inside the fetch could not help but be reported as a failure."""
        preamble = _js_slice(source, '        async fetchAndRender() {',
                             '            try {')
        assert 'const url = this.buildUrl();' in preamble
        assert REFUSAL_BLOCK.search(preamble) is not None, (
            'the refusal no longer hides, announces and returns as one block')
        assert 'console.warn' not in preamble


PRODUCT_DROPDOWNS = ['category_path-suggestions', 'tags-suggestions']
ITEM_DROPDOWNS = ['thread_size-suggestions', 'location-suggestions',
                  'sub_location-suggestions', 'purchase_location-suggestions',
                  'vendor-suggestions']


def _assert_renders_the_class(response, url, dropdown_ids):
    assert response.status_code == 200, f'{url} returned {response.status_code}'
    body = response.get_data(as_text=True)
    for dropdown_id in dropdown_ids:
        match = re.search(
            r'''<div\b[^>]*\bid=["']%s["'][^>]*>''' % re.escape(dropdown_id),
            body)
        assert match is not None, f'{url} did not render #{dropdown_id}'
        assert 'suggestions-menu' in match.group(0), (
            f'{url}: #{dropdown_id} is missing the suggestions-menu class')
        # Scoped to the dropdown's own tag rather than searched for across the
        # whole page, for the same reason the template-level check is scoped:
        # those three declarations are a reasonable inline style on some
        # unrelated scrollable overlay, and failing the page for it would be
        # wrong advice.
        assert LEGACY_INLINE_STYLE not in match.group(0), (
            f'{url}: #{dropdown_id} still inlines the geometry')


@pytest.mark.unit
class TestRenderedForms:
    """The template text is only half the claim; these pages are what the
    browser is actually handed.

    Both the add AND the edit form of each entity are exercised. Ten of the
    sixteen suggestion divs live on the two edit templates, which are separate
    files carrying their own copies of this markup — covering only the add
    pages would leave the majority of the change verified by text scan alone.
    """

    @pytest.mark.parametrize('url, dropdown_ids', [
        ('/products/add', PRODUCT_DROPDOWNS),
        ('/inventory/add', ITEM_DROPDOWNS),
    ], ids=['product-add', 'item-add'])
    def test_the_add_form_renders_the_shared_class(self, client, url,
                                                   dropdown_ids):
        _assert_renders_the_class(client.get(url), url, dropdown_ids)

    def test_the_product_edit_form_renders_the_shared_class(self, client,
                                                            test_storage):
        from app.mariadb_catalog_service import CatalogService

        product_id = CatalogService(test_storage).create_product(
            description='Autocomplete markup seed')
        url = f'/products/edit/{product_id}'
        _assert_renders_the_class(client.get(url), url, PRODUCT_DROPDOWNS)

    def test_the_item_edit_form_renders_the_shared_class(self, client):
        created = client.post('/api/inventory/items', json={
            'item_type': 'Threaded Rod', 'shape': 'Round', 'material': 'Steel',
            'location': 'Markup Shelf', 'sub_location': 'Bin 1',
            'vendor': 'Markup Vendor', 'purchase_location': 'Markup Vendor',
            'thread_series': 'UNC', 'thread_size': '1/4-20',
            'length': 100, 'active': True,
        })
        assert created.status_code == 200, created.get_data(as_text=True)
        ja_id = created.get_json()['created_ja_ids'][0]
        url = f'/inventory/edit/{ja_id}'
        _assert_renders_the_class(client.get(url), url, ITEM_DROPDOWNS)
