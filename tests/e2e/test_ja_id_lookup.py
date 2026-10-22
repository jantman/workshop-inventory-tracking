"""
E2E tests for opening an inventory item by JA ID from the header scan box.

Feature 067 folded the old JA ID Quick Lookup box into the scan box: a JA ID
scanned or typed there opens that item's edit page, and the header carries one
code-entry box.
"""

import re

import pytest
from playwright.sync_api import expect


ITEM = {
    "ja_id": "JA200001",
    "item_type": "Bar",
    "shape": "Round",
    "material": "Carbon Steel",
    "length": 12.0,
    "width": 1.0,
    "location": "Workshop",
    "notes": "Test item for JA ID scan",
    "active": True,
}


def enter_in_scan_box(page, text):
    """Type into the header scan box and press Enter, as an operator would"""
    scan_input = page.locator('#global-scan-input')
    expect(scan_input).to_be_visible()
    scan_input.fill(text)
    scan_input.press('Enter')


@pytest.mark.e2e
def test_a_ja_id_opens_the_items_edit_page(page, live_server):
    live_server.add_test_data([ITEM])
    page.goto(f'{live_server.url}/inventory')

    enter_in_scan_box(page, 'JA200001')

    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA200001')
    expect(page.locator('#ja_id')).to_have_value('JA200001')


@pytest.mark.e2e
def test_a_lowercase_ja_id_opens_the_same_page(page, live_server):
    live_server.add_test_data([ITEM])
    page.goto(f'{live_server.url}/inventory')

    enter_in_scan_box(page, 'ja200001')

    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA200001')
    expect(page.locator('#ja_id')).to_have_value('JA200001')


@pytest.mark.e2e
def test_a_nonexistent_ja_id_says_not_found(page, live_server):
    """FR-003: answered as the old box answered it, not with a product search"""
    page.goto(f'{live_server.url}/inventory')

    enter_in_scan_box(page, 'JA999999')

    expect(page).to_have_url(f'{live_server.url}/inventory')
    expect(page.locator('.alert-danger.alert-dismissible')).to_contain_text(
        'Item JA999999 not found'
    )


@pytest.mark.e2e
def test_a_malformed_ja_id_is_a_product_search(page, live_server):
    """Only the exact JA###### shape is a JA ID; anything else keeps its old path"""
    page.goto(f'{live_server.url}/inventory')

    enter_in_scan_box(page, 'JA12345')

    expect(page).to_have_url(re.compile(r'/products\?q=JA12345$'))


@pytest.mark.e2e
def test_the_header_has_one_code_entry_box(page, live_server):
    """FR-005: the JA ID Quick Lookup box is gone"""
    page.goto(f'{live_server.url}/inventory')

    # Server-rendered header: once the scan box is visible, the header is there.
    expect(page.locator('#global-scan-input')).to_be_visible()
    expect(page.locator('#ja-id-lookup')).to_have_count(0)
