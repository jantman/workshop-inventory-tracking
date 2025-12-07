"""
Common Table Behavior Tests

Parameterized tests that verify shared table functionality works consistently
across both inventory list and search pages.
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.search_page import SearchPage


# Test data for parameterized tests
TEST_ITEMS = [
    {
        "ja_id": "JA099001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "100",
        "width": "10",
        "location": "Test Storage A",
        "active": True
    },
    {
        "ja_id": "JA099002",
        "item_type": "Plate",
        "shape": "Rectangular",
        "material": "Aluminum",
        "length": "200",
        "width": "15",
        "location": "Test Storage B",
        "active": True
    },
    {
        "ja_id": "JA099003",
        "item_type": "Bar",
        "shape": "Square",
        "material": "Stainless Steel",
        "length": "150",
        "width": "12",
        "location": "Test Storage A",
        "active": True
    }
]


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_table_displays_items(page, live_server, page_type):
    """Test that both pages can display inventory items in table"""
    # Add test data
    live_server.add_test_data(TEST_ITEMS)

    # Navigate to appropriate page and load items
    if page_type == "list":
        test_page = InventoryListPage(page, live_server.url)
        test_page.navigate()
        test_page.wait_for_items_loaded()
    else:  # search
        test_page = SearchPage(page, live_server.url)
        test_page.navigate()
        # Search for all items (empty criteria shows all)
        test_page.click_search()

    # Verify all items are displayed
    test_page.assert_table_has_rows(3)
    test_page.assert_item_visible("JA099001")
    test_page.assert_item_visible("JA099002")
    test_page.assert_item_visible("JA099003")


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_table_item_selection(page, live_server, page_type):
    """Test that item selection works on both pages"""
    # Add test data
    live_server.add_test_data(TEST_ITEMS)

    # Navigate to appropriate page and load items
    if page_type == "list":
        test_page = InventoryListPage(page, live_server.url)
        test_page.navigate()
        test_page.wait_for_items_loaded()
    else:  # search
        test_page = SearchPage(page, live_server.url)
        test_page.navigate()
        test_page.click_search()

    # Test individual selection
    test_page.select_item("JA099001")
    assert test_page.get_selected_count() == 1

    test_page.select_item("JA099002")
    assert test_page.get_selected_count() == 2

    # Test select none
    test_page.select_none_items()
    assert test_page.get_selected_count() == 0

    # Test select all
    test_page.select_all_items()
    assert test_page.get_selected_count() == 3


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_table_column_values(page, live_server, page_type):
    """Test that column values are correctly displayed"""
    # Add test data with one specific item
    test_item = {
        "ja_id": "JA099999",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Brass",
        "length": "250",
        "width": "20",
        "location": "Test Location",
        "active": True
    }
    live_server.add_test_data([test_item])

    # Navigate to appropriate page and load items
    if page_type == "list":
        test_page = InventoryListPage(page, live_server.url)
        test_page.navigate()
        test_page.wait_for_items_loaded()
    else:  # search
        test_page = SearchPage(page, live_server.url)
        test_page.navigate()
        test_page.click_search()

    # Verify column values
    test_page.assert_item_visible("JA099999")
    test_page.assert_column_value("JA099999", "type", "Bar")
    test_page.assert_column_value("JA099999", "shape", "Round")
    test_page.assert_column_value("JA099999", "material", "Brass")
    test_page.assert_column_value("JA099999", "location", "Test Location")


@pytest.mark.e2e
@pytest.mark.parametrize("page_type", ["list", "search"])
def test_table_empty_state(page, live_server, page_type):
    """Test that both pages handle empty table state correctly"""
    # Don't add any test data - tables should be empty

    # Navigate to appropriate page
    if page_type == "list":
        test_page = InventoryListPage(page, live_server.url)
        test_page.navigate()
        test_page.wait_for_items_loaded()
        # List page filters to active items by default, so if there are no
        # active items, the table should be empty
    else:  # search
        test_page = SearchPage(page, live_server.url)
        test_page.navigate()
        # Search with criteria that matches nothing
        test_page.search_by_ja_id("JA999999")

    # Verify empty state
    # Note: We can't use assert_table_empty() directly because pages might
    # show "no results" message instead of an empty table
    assert test_page.get_table_row_count() == 0
