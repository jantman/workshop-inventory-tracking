"""
E2E Tests for Pagination Visibility with Inactive Items (Bug 4)

Tests to reproduce bug where pagination is not shown when filtering
to inactive items, even when there are more than 25 results.
"""

import re
import pytest
from playwright.sync_api import expect
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_pagination_shows_for_inactive_items(page, live_server):
    """Test that pagination controls are visible when filtering to inactive items (Bug 4)

    Expected to FAIL initially: When there are 30 inactive items, pagination
    should show but currently does not, leaving no indication that there are
    more results beyond the first 25.
    """
    # Create 30 inactive test items (more than default page size of 25)
    test_items = []
    for i in range(1, 31):
        test_items.append({
            "ja_id": f"JA{303000 + i:06d}",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": 12.0 + i,
            "width": 0.5,
            "location": f"Storage {chr(65 + (i % 5))}",  # A, B, C, D, E
            "notes": f"Inactive test item {i}",
            "active": False
        })

    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Change status filter to "Inactive Only"
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')

    # Wait for items to load
    list_page.wait_for_items_loaded()

    # Verify items are displayed
    items = list_page.get_inventory_items()
    assert len(items) > 0, "Should display some inactive items"

    # After fix, pagination container should be visible
    pagination_container = page.locator('#pagination-container')
    expect(pagination_container).to_be_visible()
    expect(pagination_container).not_to_have_class('d-none')

    # Verify pagination info shows correct total
    items_total = page.locator('#items-total')
    expect(items_total).to_contain_text('30')

    # Verify showing first page range
    items_start = page.locator('#items-start')
    items_end = page.locator('#items-end')
    expect(items_start).to_contain_text('1')
    expect(items_end).to_contain_text('25')

    # Verify pagination buttons exist
    pagination_buttons = page.locator('#pagination .page-item')
    expect(pagination_buttons.first).to_be_visible()


@pytest.mark.e2e
def test_pagination_navigation_for_inactive_items(page, live_server):
    """Test navigating through pages of inactive items (Bug 4)

    Expected to FAIL initially: Pagination controls should allow navigation
    to view items 26-30, but pagination is not shown.
    """
    # Create 30 inactive test items
    test_items = []
    for i in range(1, 31):
        test_items.append({
            "ja_id": f"JA{304000 + i:06d}",
            "item_type": "Plate",
            "shape": "Flat",
            "material": "Aluminum",
            "length": 24.0,
            "width": 12.0,
            "thickness": 0.25,
            "location": "Storage D",
            "notes": f"Inactive plate {i}",
            "active": False
        })

    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Filter to inactive only
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')
    list_page.wait_for_items_loaded()

    # Verify we're on page 1 showing items 1-25
    items_start = page.locator('#items-start')
    items_end = page.locator('#items-end')
    expect(items_start).to_contain_text('1')
    expect(items_end).to_contain_text('25')

    # Find and click "Next" button or page "2" button
    next_button = page.locator('#pagination .page-item:has-text("Next") a')
    expect(next_button).to_be_visible()
    expect(next_button).not_to_have_class('disabled')

    next_button.click()

    # Wait for page to update
    page.wait_for_timeout(500)

    # Verify we're now on page 2 showing items 26-30
    expect(items_start).to_contain_text('26')
    expect(items_end).to_contain_text('30')

    # Verify 5 items are displayed on page 2
    items = list_page.get_inventory_items()
    assert len(items) == 5, "Page 2 should show 5 items (items 26-30)"


@pytest.mark.e2e
def test_pagination_hides_when_results_fit_one_page(page, live_server):
    """Test that pagination is hidden when all results fit on one page

    This ensures pagination only shows when necessary.
    """
    # Create only 10 inactive items (less than default page size of 25)
    test_items = []
    for i in range(1, 11):
        test_items.append({
            "ja_id": f"JA{305000 + i:06d}",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": 18.0,
            "width": 1.0,
            "location": "Storage E",
            "notes": f"Inactive item {i}",
            "active": False
        })

    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Filter to inactive only
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')
    list_page.wait_for_items_loaded()

    # Verify all 10 items are displayed
    items = list_page.get_inventory_items()
    assert len(items) == 10, "All 10 items should be displayed"

    # Pagination should be hidden (no need for it with only 10 items)
    pagination_container = page.locator('#pagination-container')
    expect(pagination_container).to_have_class(re.compile(r'd-none'))


@pytest.mark.e2e
def test_pagination_updates_with_items_per_page_change(page, live_server):
    """Test that pagination updates when changing items per page

    Ensures pagination controls properly update when user changes
    the number of items displayed per page.
    """
    # Create 30 inactive items
    test_items = []
    for i in range(1, 31):
        test_items.append({
            "ja_id": f"JA{306000 + i:06d}",
            "item_type": "Bar",
            "shape": "Hex",
            "material": "Carbon Steel",
            "length": 24.0,
            "width": 1.25,
            "location": "Storage F",
            "notes": f"Test item {i}",
            "active": False
        })

    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Filter to inactive only
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')
    list_page.wait_for_items_loaded()

    # Initially showing 25 per page, verify we're on page 1 of 2
    items_total = page.locator('#items-total')
    expect(items_total).to_contain_text('30')

    # Change to 10 items per page
    items_per_page_select = page.locator('#items-per-page')
    items_per_page_select.select_option('10')

    # Wait for update
    page.wait_for_timeout(500)

    # Now should be showing items 1-10 of 30 (page 1 of 3)
    items_start = page.locator('#items-start')
    items_end = page.locator('#items-end')
    expect(items_start).to_contain_text('1')
    expect(items_end).to_contain_text('10')
    expect(items_total).to_contain_text('30')

    # Verify exactly 10 items are visible
    items = list_page.get_inventory_items()
    assert len(items) == 10, "Should display exactly 10 items per page"

    # Change to 50 items per page (all items should fit on one page now)
    items_per_page_select.select_option('50')
    page.wait_for_timeout(500)

    # All 30 items should now be visible on one page
    items = list_page.get_inventory_items()
    assert len(items) == 30, "All 30 items should be displayed with 50 per page"

    # Pagination should be hidden (only 1 page needed)
    pagination_container = page.locator('#pagination-container')
    expect(pagination_container).to_have_class(re.compile(r'd-none'))
