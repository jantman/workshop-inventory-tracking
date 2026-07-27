"""
E2E tests for the ARIA combobox semantics of the shared field autocomplete
(``app/static/js/field-autocomplete.js``, DW-40).

These assertions can only be made in a real browser. The semantics are written
by the component at runtime — the templates carry no ARIA at all — so nothing
in the rendered HTML shows them, and there is no JS test infra in this project
to exercise the component directly. Every attribute below therefore has exactly
one place it can be checked: here.

What is actually at stake is that the dropdown is *usable without sight*.
Before this, an open dropdown was an anonymous ``<div>`` of links, the arrow-key
selection was conveyed by a CSS class alone, and Story 3.1's ``+ Create "…"``
entry differed from a stored suggestion only by font weight — three facts a
screen reader has no way to reach. So the tests pin the accessibility-tree
facts (roles, ``aria-selected``, ``aria-activedescendant``, the live region)
rather than anything visual.

Isolation note: ``tests/e2e/test_server.py``'s ``clear_test_data()`` truncates
inventory items and the catalog tables, and ``live_server`` is function-scoped,
so every test — and every ``--reruns`` replay, which re-runs setup — starts
from an empty database. The item-form tests therefore know exactly what they
seeded and may count rows; the product-form tests still mint a run-unique
category prefix, in the style of ``tests/e2e/test_category_autocomplete.py``.
"""

import re
import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.pages.add_item_page import AddItemPage

#: The five item-form fields plus the two product-form ones — every target in
#: the component's auto-init list. The point of doing the wiring in JS is that
#: it reaches all of them, so the sweep test checks all of them.
ITEM_FORM_FIELDS = ['thread_size', 'purchase_location', 'vendor', 'location',
                    'sub_location']
PRODUCT_FORM_FIELDS = ['category_path', 'tags']

#: Matches any attribute value, so `not_to_have_attribute(name, ANY_VALUE)`
#: asserts the attribute is ABSENT. Used instead of a bare
#: `get_attribute(...) is None`, which reads once and cannot retry — every one
#: of these checks follows an asynchronous UI action, in a suite the project
#: runs with `--reruns`.
ANY_VALUE = re.compile(r'[\s\S]*')


def _seed_items(live_server, extra=()):
    """Seed items via the live server's REST API and return their JA IDs.

    The three defaults give three distinct vendors — the three-row dropdown the
    option and arrow-key tests count on. `extra` appends further payloads for
    the tests that need a different row count.

    Modeled on ``tests/e2e/test_field_autocomplete.py``'s helper and copied
    rather than shared: that module's copy seeds the vendors and locations
    *its* assertions count, and the two would have to stay independently
    editable anyway. Promoting one seeder to ``tests/e2e/conftest.py`` would
    mean editing that file, which this change is required to leave untouched.
    """
    import requests

    payloads = [
        {
            'item_type': 'Threaded Rod', 'shape': 'Round', 'material': 'Steel',
            'location': 'ARIA Shelf', 'sub_location': 'Top Bin',
            'vendor': 'McMaster-Carr', 'purchase_location': 'McMaster-Carr',
            'thread_series': 'UNC', 'thread_size': '1/4-20',
            'length': 100, 'active': True,
        },
        {
            'item_type': 'Threaded Rod', 'shape': 'Round', 'material': 'Steel',
            'location': 'ARIA Shelf', 'sub_location': 'Bottom Bin',
            'vendor': 'Online Metals', 'purchase_location': 'OnlineMetals.com',
            'thread_series': 'Metric', 'thread_size': 'M10x1.5',
            'length': 100, 'active': True,
        },
        {
            'item_type': 'Threaded Rod', 'shape': 'Round', 'material': 'Steel',
            'location': 'ARIA Rack', 'sub_location': 'Slot A',
            'vendor': 'Grainger', 'purchase_location': 'Grainger',
            'thread_series': 'UNC', 'thread_size': '1/2-13',
            'length': 100, 'active': True,
        },
    ]
    payloads.extend(extra)
    ja_ids = []
    for payload in payloads:
        response = requests.post(
            f'{live_server.url}/api/inventory/items', json=payload, timeout=15)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get('success') is True, response.text
        ja_ids.extend(body.get('created_ja_ids') or [])
    return ja_ids


def _live_region(page, field):
    """The component's polite announcer for `field`.

    Deliberately located as the dropdown's next sibling rather than by class:
    that placement is itself part of the contract, because a `role="listbox"`
    may only own `role="option"` children and a live region inside it would not
    be one.
    """
    return page.locator(f'#{field}-suggestions + [role="status"]')


def _open_vendor_dropdown(page, live_server):
    """Seed, load the Add Item form, and open the three-entry vendor dropdown.

    Waiting for the third row before returning is what makes the arrow-key
    assertions deterministic: focusing the field fires an immediate fetch, and
    a dropdown caught mid-render would have fewer options than the test walks.
    """
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    vendor = page.locator('#vendor')
    vendor.click()
    dropdown = page.locator('#vendor-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    options = dropdown.locator('.dropdown-item')
    expect(options).to_have_count(3, timeout=5000)
    return vendor, dropdown, options


def _unique_prefix(label):
    """A category segment no other test (or rerun) can have created."""
    return f'e2earia-{label}-{uuid.uuid4().hex[:8]}'


@pytest.mark.e2e
def test_idle_inputs_are_collapsed_comboboxes(page, live_server):
    """Before anything is typed the input already advertises what it is.

    A screen-reader user has to know a suggestion list exists *before*
    triggering it; the combobox role and `aria-controls` are what say so. And
    with nothing open, `aria-expanded` must read false and `aria-activedescendant`
    must be absent — a stale pointer to an option that does not exist is worse
    than no pointer.
    """
    AddItemPage(page, live_server.url).navigate()

    for field in ITEM_FORM_FIELDS:
        field_input = page.locator(f'#{field}')
        expect(field_input).to_have_attribute('role', 'combobox')
        expect(field_input).to_have_attribute('aria-autocomplete', 'list')
        expect(field_input).to_have_attribute(
            'aria-controls', f'{field}-suggestions')
        expect(field_input).to_have_attribute('aria-expanded', 'false')
        expect(field_input).not_to_have_attribute(
            'aria-activedescendant', ANY_VALUE)


@pytest.mark.e2e
def test_an_open_dropdown_is_a_listbox_of_uniquely_identified_options(
        page, live_server):
    """The open dropdown is a real listbox, and every entry is an option with
    an id of its own.

    The ids are not cosmetic: `aria-activedescendant` can only reference an
    element that has one, so duplicated or missing ids would silently break the
    keyboard-selection announcement even though the roles all looked right.
    """
    _vendor, dropdown, options = _open_vendor_dropdown(page, live_server)

    expect(dropdown).to_have_attribute('role', 'listbox')
    # Named from the <label for="vendor"> already on the page, so the listbox
    # cannot end up called something other than the field beside it.
    expect(dropdown).to_have_attribute('aria-label', 'Vendor suggestions')

    ids = []
    for index in range(3):
        option = options.nth(index)
        expect(option).to_have_attribute('role', 'option')
        expect(option).to_have_attribute('aria-selected', 'false')
        # Focus stays in the input; without this the anchors are tab stops and
        # Tab walks into the suggestion list instead of to the next control.
        expect(option).to_have_attribute('tabindex', '-1')
        option_id = option.get_attribute('id')
        assert option_id, f'option {index} has no id to be referenced by'
        ids.append(option_id)
    assert len(set(ids)) == 3, f'option ids are not unique: {ids}'

    expect(page.locator('#vendor')).to_have_attribute('aria-expanded', 'true')
    expect(_live_region(page, 'vendor')).to_have_text('3 suggestions available')


@pytest.mark.e2e
def test_the_required_marker_is_stripped_from_the_listbox_name(
        page, live_server):
    """Location's visible label is "Location *". The asterisk is a sighted
    convention for "required" — announcing "Location star suggestions" is
    noise, and the input's own `required` already carries the fact."""
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    page.locator('#location').click()
    dropdown = page.locator('#location-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    expect(dropdown).to_have_attribute('aria-label', 'Location suggestions')


@pytest.mark.e2e
def test_arrow_keys_move_aria_selected_and_activedescendant_together(
        page, live_server):
    """Arrow-key selection is exposed, not just painted.

    `highlight()` used to convey the active entry with a CSS class alone, which
    the accessibility tree cannot see at all. The two facts have to move as
    one: exactly one option `aria-selected="true"`, and the input pointing at
    that same option. Either one alone is a lie.
    """
    vendor, _dropdown, options = _open_vendor_dropdown(page, live_server)

    def assert_active(position):
        active_id = options.nth(position).get_attribute('id')
        for index in range(3):
            expect(options.nth(index)).to_have_attribute(
                'aria-selected', 'true' if index == position else 'false')
        expect(vendor).to_have_attribute('aria-activedescendant', active_id)

    vendor.press('ArrowDown')
    assert_active(0)

    vendor.press('ArrowDown')
    assert_active(1)

    vendor.press('ArrowUp')
    assert_active(0)


@pytest.mark.e2e
def test_arrow_up_from_nothing_wraps_to_the_last_option(page, live_server):
    """ArrowUp on a freshly opened dropdown wraps to the bottom — the existing
    behavior — and the exposure follows it there rather than being applied only
    on the way down."""
    vendor, _dropdown, options = _open_vendor_dropdown(page, live_server)

    vendor.press('ArrowUp')

    last_id = options.nth(2).get_attribute('id')
    expect(options.nth(2)).to_have_attribute('aria-selected', 'true')
    expect(options.nth(0)).to_have_attribute('aria-selected', 'false')
    expect(options.nth(1)).to_have_attribute('aria-selected', 'false')
    expect(vendor).to_have_attribute('aria-activedescendant', last_id)


@pytest.mark.e2e
def test_escape_collapses_the_combobox_and_drops_the_active_option(
        page, live_server):
    """Dismissing has to reach the accessibility tree too.

    A dropdown hidden with `display: none` while the input still reports
    `aria-expanded="true"` and points at an option leaves a screen-reader user
    navigating a list that is no longer on screen.
    """
    vendor, dropdown, options = _open_vendor_dropdown(page, live_server)

    # Escape has to have something to clear, so wait for the highlight to land
    # before dismissing.
    vendor.press('ArrowDown')
    expect(options.nth(0)).to_have_attribute('aria-selected', 'true')

    vendor.press('Escape')

    expect(dropdown).to_be_hidden()
    expect(vendor).to_have_attribute('aria-expanded', 'false')
    expect(vendor).not_to_have_attribute('aria-activedescendant', ANY_VALUE)
    # Nothing is on offer, so the announcer must not still be claiming three.
    expect(_live_region(page, 'vendor')).to_be_empty()


@pytest.mark.e2e
def test_clicking_away_collapses_the_combobox(page, live_server):
    """Escape is not the only way out. Blur and an outside click dismiss the
    dropdown too, and each is its own code path (`blur` schedules the dismiss,
    the document click handler fires it immediately) — a collapse that reached
    the accessibility tree on only one of them would leave the input claiming
    an expanded list on the others."""
    vendor, dropdown, _options = _open_vendor_dropdown(page, live_server)

    # A click on the page background: outside the input and outside the
    # dropdown, so both the document handler and the blur timer are in play.
    page.locator('h1, h2').first.click()

    expect(dropdown).to_be_hidden()
    expect(vendor).to_have_attribute('aria-expanded', 'false')
    expect(vendor).not_to_have_attribute('aria-activedescendant', ANY_VALUE)


@pytest.mark.e2e
def test_a_single_match_is_announced_in_the_singular(page, live_server):
    """"1 suggestions available" is the kind of wording that makes a synthetic
    voice sound broken, and singular/plural is the one branch in the
    announcement string."""
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    vendor = page.locator('#vendor')
    # Only "Grainger" of the three seeded vendors contains "grain".
    vendor.fill('grain')

    expect(page.locator('#vendor-suggestions .dropdown-item')).to_have_count(
        1, timeout=5000)
    expect(_live_region(page, 'vendor')).to_have_text('1 suggestion available')


@pytest.mark.e2e
def test_the_active_option_is_scrolled_into_view(page, live_server):
    """`aria-activedescendant` must reference a VISIBLE option, and the
    `active` class is no use to a sighted keyboard user below the fold.

    The dropdown caps at 200px and the component asks for up to ten rows, so
    arrow-keying to the last entry of a full list puts it outside the scroll
    box unless the component scrolls it back.
    """
    extra = [
        {
            'item_type': 'Threaded Rod', 'shape': 'Round', 'material': 'Steel',
            'location': 'ARIA Shelf', 'sub_location': 'Top Bin',
            'vendor': f'Scrolling Vendor {n:02d}',
            'purchase_location': 'ARIA', 'thread_series': 'UNC',
            'thread_size': '1/4-20', 'length': 100, 'active': True,
        }
        for n in range(10)
    ]
    _seed_items(live_server, extra=extra)
    AddItemPage(page, live_server.url).navigate()

    vendor = page.locator('#vendor')
    vendor.fill('Scrolling Vendor')
    options = page.locator('#vendor-suggestions .dropdown-item')
    # `fill()` focuses first, and focus fires an immediate UNFILTERED fetch.
    # Thirteen distinct vendors are seeded against a limit of ten, so that
    # render also produces exactly ten rows — a bare count check here would be
    # satisfied by it, and the debounced filtered fetch would then land in the
    # middle of the arrow-keying below, calling replaceChildren() and resetting
    # activeIndex. Waiting for the seeded vendors to be gone is what pins the
    # FILTERED render: they sort ahead of "Scrolling Vendor" alphabetically, so
    # the unfiltered top ten always contains them and the filtered ten never
    # can. Once it is on screen no later render is possible — the stale
    # response is dropped by the requestSeq guard.
    expect(options).to_have_count(10, timeout=5000)
    expect(page.locator(
        '#vendor-suggestions .dropdown-item', has_text='McMaster-Carr'
    )).to_have_count(0)

    for _ in range(10):
        vendor.press('ArrowDown')

    last = options.nth(9)
    expect(last).to_have_attribute('aria-selected', 'true')
    # Clipped by the dropdown's own `overflow-y: auto` counts as out of view:
    # the intersection is computed against every clipping ancestor.
    expect(last).to_be_in_viewport()


@pytest.mark.e2e
def test_a_dropdown_whose_input_has_no_label_is_still_named(page, live_server):
    """The `listboxLabel()` fallback. Every wired field has a `<label for=…>`
    today, so the branch is unreachable through the app — but the component is
    exported for programmatic use and the next field to be wired might arrive
    without one. An unnamed listbox is announced as nothing at all.
    """
    AddItemPage(page, live_server.url).navigate()

    label = page.evaluate(
        """() => {
            const host = document.createElement('div');
            host.innerHTML =
                '<input id="e2e-unlabelled">' +
                '<div id="e2e-unlabelled-suggestions"></div>';
            document.body.appendChild(host);
            new window.FieldAutocomplete(
                { inputId: 'e2e-unlabelled', field: 'purchase_location' });
            return document.getElementById('e2e-unlabelled-suggestions')
                           .getAttribute('aria-label');
        }"""
    )
    assert label == 'purchase location suggestions', label


@pytest.mark.e2e
def test_a_query_that_matches_nothing_is_announced(page, live_server):
    """"No suggestions" is information. Sighted users get it from a dropdown
    that visibly fails to appear; without the announcement a screen-reader user
    cannot tell an empty result from a request that never came back."""
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    vendor = page.locator('#vendor')
    # A vendor no seeded item carries, so the filtered response is empty.
    vendor.fill('zzz-no-such-vendor')

    expect(_live_region(page, 'vendor')).to_have_text(
        'No suggestions', timeout=5000)
    expect(page.locator('#vendor-suggestions')).to_be_hidden()
    expect(vendor).to_have_attribute('aria-expanded', 'false')


@pytest.mark.e2e
def test_the_create_entry_is_distinguishable_from_a_stored_suggestion(
        page, live_server):
    """The `+ Create "…"` entry differs from a stored suggestion in one
    visible way — `fw-semibold` — and font weight is invisible to a screen
    reader. So it also carries `data-create` and a hidden qualifier, and a
    stored suggestion carries neither.

    The qualifier is a hidden SUFFIX rather than an `aria-label`, so the
    accessible name still contains the visible text (WCAG 2.5.3, label-in-name)
    and a voice-control user can still say "Create". This test asserts that
    shape directly: the element's text nodes — everything outside the hidden
    span — must still be exactly the visible string.
    """
    prefix = _unique_prefix('create')
    canonical = f'{prefix}/power supplies'

    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()

    category.fill(f'{prefix.upper()}/Power Supplies/')

    dropdown = page.locator('#category_path-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    # The path is unique to this run, so nothing can match it: the create entry
    # is the only row. Waiting for that also proves the FILTERED response is on
    # screen rather than the unfiltered focus render.
    expect(dropdown.locator('.dropdown-item')).to_have_count(1, timeout=5000)

    create = dropdown.locator('.dropdown-item[data-create="true"]')
    expect(create).to_have_count(1)
    expect(create).to_have_attribute('role', 'option')
    qualifier = create.locator('span.visually-hidden')
    expect(qualifier).to_have_count(1)
    assert qualifier.text_content().strip(), \
        'the create entry has an empty hidden qualifier'

    visible_text = create.evaluate(
        """el => Array.from(el.childNodes)
                     .filter(node => node.nodeType === Node.TEXT_NODE)
                     .map(node => node.textContent).join('')""")
    assert visible_text == f'+ Create "{canonical}"', visible_text
    # ...and the qualifier really is appended to it, not substituted for it.
    assert create.text_content().startswith(f'+ Create "{canonical}"')

    # The create row is NOT a match. Counting it as one would announce
    # "1 suggestion available" for a path nothing in the catalog holds —
    # telling a screen-reader user the opposite of what the visible
    # `+ Create "…"` wording says.
    expect(_live_region(page, 'category_path')).to_have_text(
        f'No suggestions, plus an option to create "{canonical}"')

    # Accept it and save, so the same path comes back as an ORDINARY
    # suggestion on the next form — the other half of the comparison.
    create.click()
    expect(category).to_have_value(canonical)
    # Selecting ends the interaction: the combobox has to report itself
    # collapsed, not merely look it.
    expect(dropdown).to_be_hidden()
    expect(category).to_have_attribute('aria-expanded', 'false')
    expect(category).not_to_have_attribute('aria-activedescendant', ANY_VALUE)
    page.locator('#description').fill('E2E aria create entry')
    page.locator('button[type="submit"]').click()
    expect(page.locator('body')).to_contain_text(canonical, timeout=10000)

    page.goto(f'{live_server.url}/products/add')
    category = page.locator('#category_path')
    expect(category).to_be_visible()
    category.fill(canonical)

    dropdown = page.locator('#category_path-suggestions')
    expect(dropdown).to_be_visible(timeout=5000)
    # The path is unique to this run and now stored, so exactly one row can
    # match it — and it is a stored suggestion, not a create offer.
    expect(dropdown.locator('.dropdown-item')).to_have_count(1, timeout=5000)
    stored = dropdown.locator('.dropdown-item').first
    expect(stored).to_have_attribute('role', 'option')
    expect(stored).to_have_text(canonical)
    assert stored.get_attribute('data-create') is None, \
        'a stored suggestion is being marked as a create entry'
    expect(stored.locator('span.visually-hidden')).to_have_count(0)


@pytest.mark.e2e
# Explicit ids: the default would embed the URL, and `tests/conftest.py`'s
# debug-capture fixture mkdir()s a directory named after the test id — a
# slash in it makes that a nested path whose parent does not exist, so the
# test errors in setup before it runs.
@pytest.mark.parametrize('path, fields', [
    ('/inventory/add', ITEM_FORM_FIELDS),
    ('/products/add', PRODUCT_FORM_FIELDS),
], ids=['item_form', 'product_form'])
def test_every_wired_field_is_a_combobox_owning_its_own_listbox(
        page, live_server, path, fields):
    """The sweep that justifies doing this in JS at all.

    Seven fields across three forms are wired by one auto-init list, so one
    implementation either reaches all of them or none. Hand-written per-template
    attributes would have to be checked field by field — and would eventually
    disagree.

    `aria-controls` is resolved rather than merely compared: an id that names
    nothing, or names another field's dropdown, is a pointer a screen reader
    follows into the wrong list.
    """
    page.goto(f'{live_server.url}{path}')
    expect(page.locator(f'#{fields[0]}')).to_have_count(1)

    for field in fields:
        field_input = page.locator(f'#{field}')
        expect(field_input).to_have_attribute('role', 'combobox')
        controls = field_input.get_attribute('aria-controls')
        assert controls == f'{field}-suggestions', \
            f'#{field} controls {controls!r}'
        resolved_role = page.evaluate(
            '(id) => { const el = document.getElementById(id);'
            '          return el && el.getAttribute("role"); }',
            controls)
        assert resolved_role == 'listbox', \
            f'#{field}: aria-controls={controls!r} resolves to {resolved_role!r}'


@pytest.mark.e2e
def test_the_edit_forms_are_wired_too(page, live_server):
    """Ten of the sixteen suggestion divs live on the two EDIT templates.

    They are separate files carrying their own copy of this markup, and the
    add forms are the ones every other test in this module opens — so without
    this the majority of the change would be verified by template text scan
    alone, never in a browser.
    """
    ja_id = _seed_items(live_server)[0]

    # Product edit: create one through the add form, which redirects to the
    # new product's detail page, and read its id back out of the URL.
    page.goto(f'{live_server.url}/products/add')
    page.locator('#description').fill('E2E aria edit-form seed')
    page.locator('button[type="submit"]').click()
    expect(page).to_have_url(re.compile(r'/products/\d+$'), timeout=10000)
    product_id = page.url.rstrip('/').rsplit('/', 1)[-1]

    for path, fields in (
        (f'/products/edit/{product_id}', PRODUCT_FORM_FIELDS),
        (f'/inventory/edit/{ja_id}', ITEM_FORM_FIELDS),
    ):
        page.goto(f'{live_server.url}{path}')
        for field in fields:
            field_input = page.locator(f'#{field}')
            expect(field_input).to_have_attribute('role', 'combobox')
            expect(field_input).to_have_attribute(
                'aria-controls', f'{field}-suggestions')
            expect(page.locator(f'#{field}-suggestions')).to_have_attribute(
                'role', 'listbox')


@pytest.mark.e2e
def test_the_material_dropdown_is_left_alone(page, live_server):
    """`#material-suggestions` is not this component's: it shares the geometry
    class and nothing else.

    It is filled by ``app/static/js/inventory-add.js``
    (``setupMaterialAutocomplete``/``showMaterialMatches``) on the add form and
    by an inline script in ``app/templates/inventory/edit.html`` on the edit
    form. ``MaterialSelector`` is a third widget again and builds its own
    ``.material-suggestions`` container rather than using this div — worth
    stating precisely, because it decides which file a fix has to touch.

    Read as a scope boundary, NOT as approval: Material is a required field and
    its dropdown remains without ARIA semantics of its own, tracked separately
    on the deferred-work ledger. So the assertion is deliberately narrow — that
    THIS component did not attach here, evidenced by the absence of the live
    region it always creates. Asserting the div carries no `role` at all would
    instead turn this test red the day the material widget is given the
    semantics the ledger says it needs.
    """
    AddItemPage(page, live_server.url).navigate()

    material_dropdown = page.locator('#material-suggestions')
    expect(material_dropdown).to_have_class(re.compile(r'\bsuggestions-menu\b'))
    expect(page.locator('#material-suggestions-status')).to_have_count(0)
    expect(page.locator('#material')).not_to_have_attribute(
        'aria-controls', ANY_VALUE)
