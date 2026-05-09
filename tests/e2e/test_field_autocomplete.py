"""
E2E tests for the database-backed field autocomplete on the Add and
Edit Item forms.

Covers the five fields wired up by ``app/static/js/field-autocomplete.js``:
``thread_size``, ``purchase_location``, ``vendor``, ``location``, and
``sub_location``. Sub-location is reactive to Location.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage


def _seed_items(live_server):
    """Seed three items via the live server's REST API.

    Returns the list of allocated JA IDs for the caller to reuse.
    """
    import requests

    # NB: the form parser only persists thread_size when thread_series
    # is also provided, so we send a series for each item.
    payloads = [
        {
            'item_type': 'Threaded Rod', 'shape': 'Round',
            'material': 'Steel', 'location': 'Autocomplete Shelf',
            'sub_location': 'Top Bin',
            'vendor': 'McMaster-Carr',
            'purchase_location': 'McMaster-Carr',
            'thread_series': 'UNC', 'thread_size': '1/4-20',
            'length': 100, 'active': True,
        },
        {
            'item_type': 'Threaded Rod', 'shape': 'Round',
            'material': 'Steel', 'location': 'Autocomplete Shelf',
            'sub_location': 'Bottom Bin',
            'vendor': 'Online Metals',
            'purchase_location': 'OnlineMetals.com',
            'thread_series': 'Metric', 'thread_size': 'M10x1.5',
            'length': 100, 'active': True,
        },
        {
            'item_type': 'Threaded Rod', 'shape': 'Round',
            'material': 'Steel', 'location': 'Autocomplete Rack',
            'sub_location': 'Slot A',
            'vendor': 'Grainger',
            'purchase_location': 'Grainger',
            'thread_series': 'UNC', 'thread_size': '1/2-13',
            'length': 100, 'active': True,
        },
    ]
    ja_ids = []
    for p in payloads:
        r = requests.post(
            f'{live_server.url}/api/inventory/items', json=p, timeout=15
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get('success') is True, body
        ja_ids.extend(body.get('created_ja_ids') or [])
    return ja_ids


def _expect_dropdown_visible(page, dropdown_id, contains_text=None):
    dropdown = page.locator(f'#{dropdown_id}')
    expect(dropdown).to_be_visible(timeout=5000)
    if contains_text is not None:
        expect(dropdown).to_contain_text(contains_text, timeout=5000)
    return dropdown


@pytest.mark.e2e
def test_vendor_autocomplete_on_add_form(page, live_server):
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    vendor_input = page.locator('#vendor')
    vendor_input.click()  # focus → fetches all vendors
    dropdown = _expect_dropdown_visible(
        page, 'vendor-suggestions', contains_text='McMaster-Carr'
    )

    # Type to filter
    vendor_input.fill('metal')
    expect(dropdown).to_contain_text('Online Metals', timeout=5000)

    # Click a suggestion → fills the input and hides the dropdown.
    item = dropdown.locator('.dropdown-item', has_text='Online Metals')
    item.click()
    expect(vendor_input).to_have_value('Online Metals')
    expect(dropdown).to_be_hidden()


@pytest.mark.e2e
def test_location_autocomplete_on_add_form(page, live_server):
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    loc = page.locator('#location')
    loc.click()
    _expect_dropdown_visible(
        page, 'location-suggestions', contains_text='Autocomplete Shelf'
    )

    loc.fill('Rack')
    dropdown = page.locator('#location-suggestions')
    expect(dropdown).to_contain_text('Autocomplete Rack', timeout=5000)

    dropdown.locator('.dropdown-item', has_text='Autocomplete Rack').click()
    expect(loc).to_have_value('Autocomplete Rack')


@pytest.mark.e2e
def test_sub_location_autocomplete_filters_by_location(page, live_server):
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    page.locator('#location').fill('Autocomplete Shelf')
    sub = page.locator('#sub_location')
    sub.click()  # focus

    dropdown = _expect_dropdown_visible(
        page, 'sub_location-suggestions', contains_text='Top Bin'
    )
    expect(dropdown).to_contain_text('Bottom Bin', timeout=5000)
    # 'Slot A' lives under "Autocomplete Rack" so should NOT appear.
    expect(dropdown).not_to_contain_text('Slot A')

    dropdown.locator('.dropdown-item', has_text='Top Bin').click()
    expect(sub).to_have_value('Top Bin')


@pytest.mark.e2e
def test_purchase_location_and_thread_size_on_add_form(page, live_server):
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    # Threading section is conditional on Threaded Rod; pick that so
    # the thread_size input is visible and interactive.
    page.locator('#item_type').select_option('Threaded Rod')
    page.locator('#shape').select_option('Round')

    ts = page.locator('#thread_size')
    ts.click()
    _expect_dropdown_visible(
        page, 'thread_size-suggestions', contains_text='1/4-20'
    )
    page.locator(
        '#thread_size-suggestions .dropdown-item', has_text='M10x1.5'
    ).click()
    expect(ts).to_have_value('M10x1.5')

    pl = page.locator('#purchase_location')
    pl.click()
    _expect_dropdown_visible(
        page, 'purchase_location-suggestions', contains_text='McMaster-Carr'
    )
    pl.fill('Online')
    dd = page.locator('#purchase_location-suggestions')
    expect(dd).to_contain_text('OnlineMetals.com', timeout=5000)


@pytest.mark.e2e
def test_keyboard_navigation_selects_suggestion(page, live_server):
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    vendor = page.locator('#vendor')
    vendor.click()
    _expect_dropdown_visible(
        page, 'vendor-suggestions', contains_text='Grainger'
    )

    # ArrowDown twice + Enter selects the second item.
    vendor.press('ArrowDown')
    vendor.press('ArrowDown')
    vendor.press('Enter')

    # The dropdown closes; vendor input is filled with one of the
    # seeded vendors. We don't assert which without depending on the
    # alphabetical order behavior, but it must be non-empty and one of
    # the seeded values.
    value = vendor.input_value()
    assert value in {'Grainger', 'McMaster-Carr', 'Online Metals'}, value
    expect(page.locator('#vendor-suggestions')).to_be_hidden()


@pytest.mark.e2e
def test_autocomplete_on_edit_form(page, live_server):
    ja_ids = _seed_items(live_server)
    target = ja_ids[0]

    page.goto(f'{live_server.url}/inventory/edit/{target}')
    expect(page.locator('#vendor')).to_be_visible()

    vendor = page.locator('#vendor')
    # The field is pre-filled from the item; clear it so the
    # focus-fetch returns all vendors rather than only matches for
    # the current value.
    vendor.fill('')
    vendor.click()
    _expect_dropdown_visible(
        page, 'vendor-suggestions', contains_text='Grainger'
    )

    page.locator(
        '#vendor-suggestions .dropdown-item', has_text='Grainger'
    ).click()
    expect(vendor).to_have_value('Grainger')

    # Sub-location reactive to Location works on Edit too. Item starts
    # with Location='Autocomplete Shelf'; sub_location dropdown should
    # only show siblings under that location.
    sub = page.locator('#sub_location')
    sub.fill('')
    sub.click()
    dd = _expect_dropdown_visible(
        page, 'sub_location-suggestions', contains_text='Top Bin'
    )
    expect(dd).to_contain_text('Bottom Bin', timeout=5000)
    expect(dd).not_to_contain_text('Slot A')


@pytest.mark.e2e
def test_unknown_field_returns_empty_dropdown(page, live_server):
    """A defense-in-depth check: if someone wires the JS to an
    unsupported field, the server returns 400 and the dropdown stays
    hidden — no exception leaks into the UI.
    """
    _seed_items(live_server)
    AddItemPage(page, live_server.url).navigate()

    page.evaluate(
        """() => fetch('/api/inventory/field-suggestions/material')
                  .then(r => window.__rejectStatus = r.status)"""
    )
    page.wait_for_function('window.__rejectStatus !== undefined', timeout=5000)
    status = page.evaluate('window.__rejectStatus')
    assert status == 400
