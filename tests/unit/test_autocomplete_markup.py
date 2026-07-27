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
"""

import re
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / 'app'
TEMPLATE_ROOT = APP_ROOT / 'templates'
MAIN_CSS = APP_ROOT / 'static' / 'css' / 'main.css'

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
