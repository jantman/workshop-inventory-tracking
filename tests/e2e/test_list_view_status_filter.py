"""
E2E Tests for Inventory List Status Filter

Tests to verify the status filter dropdown in the inventory list view
properly filters items by active/inactive status.
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage
from playwright.sync_api import expect


@pytest.mark.e2e
def test_status_filter_active_only(page, live_server):
    """Test 'Active Only' status filter shows only active items"""
    # Add test data with both active and inactive items
    test_items = [
        {
            "ja_id": "JA201001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "500",
            "width": "12",
            "location": "Storage A",
            "notes": "Active steel rod",
            "active": True
        },
        {
            "ja_id": "JA201002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "1000",
            "width": "500",
            "thickness": "3",
            "location": "Storage B",
            "notes": "Inactive aluminum sheet",
            "active": False
        },
        {
            "ja_id": "JA201003",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Copper",
            "length": "300",
            "width": "25",
            "wall_thickness": "2",
            "location": "Storage C",
            "notes": "Active copper tube",
            "active": True
        },
        {
            "ja_id": "JA201004",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "600",
            "width": "20",
            "location": "Storage D",
            "notes": "Inactive stainless rod",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Verify 'Active Only' is selected by default
    status_filter = page.locator("#status-filter")
    expect(status_filter).to_have_value("active")

    # Get displayed items
    items = list_page.get_inventory_items()
    ja_ids = [item["ja_id"] for item in items]

    # Should only show active items (JA201001 and JA201003)
    assert "JA201001" in ja_ids, "Active item JA201001 should be visible"
    assert "JA201003" in ja_ids, "Active item JA201003 should be visible"
    assert "JA201002" not in ja_ids, "Inactive item JA201002 should not be visible"
    assert "JA201004" not in ja_ids, "Inactive item JA201004 should not be visible"
    assert len(items) == 2, f"Expected 2 active items, found {len(items)}"


@pytest.mark.e2e
def test_status_filter_inactive_only(page, live_server):
    """Test 'Inactive Only' status filter shows only inactive items"""
    # Add test data with both active and inactive items
    test_items = [
        {
            "ja_id": "JA202001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "500",
            "width": "12",
            "location": "Storage A",
            "notes": "Active steel rod",
            "active": True
        },
        {
            "ja_id": "JA202002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "1000",
            "width": "500",
            "thickness": "3",
            "location": "Storage B",
            "notes": "Inactive aluminum sheet",
            "active": False
        },
        {
            "ja_id": "JA202003",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Copper",
            "length": "300",
            "width": "25",
            "wall_thickness": "2",
            "location": "Storage C",
            "notes": "Active copper tube",
            "active": True
        },
        {
            "ja_id": "JA202004",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "600",
            "width": "20",
            "location": "Storage D",
            "notes": "Inactive stainless rod",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Change filter to 'Inactive Only'
    status_filter = page.locator("#status-filter")
    status_filter.select_option("inactive")

    # Wait for filter to apply
    page.wait_for_timeout(1000)

    # Get displayed items
    items = list_page.get_inventory_items()
    ja_ids = [item["ja_id"] for item in items]

    # Should only show inactive items (JA202002 and JA202004)
    assert "JA202002" in ja_ids, "Inactive item JA202002 should be visible"
    assert "JA202004" in ja_ids, "Inactive item JA202004 should be visible"
    assert "JA202001" not in ja_ids, "Active item JA202001 should not be visible"
    assert "JA202003" not in ja_ids, "Active item JA202003 should not be visible"
    assert len(items) == 2, f"Expected 2 inactive items, found {len(items)}"


@pytest.mark.e2e
def test_status_filter_all_items(page, live_server):
    """Test 'All Items' status filter shows both active and inactive items"""
    # Add test data with both active and inactive items
    test_items = [
        {
            "ja_id": "JA203001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "500",
            "width": "12",
            "location": "Storage A",
            "notes": "Active steel rod",
            "active": True
        },
        {
            "ja_id": "JA203002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "1000",
            "width": "500",
            "thickness": "3",
            "location": "Storage B",
            "notes": "Inactive aluminum sheet",
            "active": False
        },
        {
            "ja_id": "JA203003",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Copper",
            "length": "300",
            "width": "25",
            "wall_thickness": "2",
            "location": "Storage C",
            "notes": "Active copper tube",
            "active": True
        },
        {
            "ja_id": "JA203004",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "600",
            "width": "20",
            "location": "Storage D",
            "notes": "Inactive stainless rod",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Change filter to 'All Items'
    status_filter = page.locator("#status-filter")
    status_filter.select_option("all")

    # Wait for filter to apply
    page.wait_for_timeout(1000)

    # Get displayed items
    items = list_page.get_inventory_items()
    ja_ids = [item["ja_id"] for item in items]

    # Should show all items (both active and inactive)
    assert "JA203001" in ja_ids, "Active item JA203001 should be visible"
    assert "JA203002" in ja_ids, "Inactive item JA203002 should be visible"
    assert "JA203003" in ja_ids, "Active item JA203003 should be visible"
    assert "JA203004" in ja_ids, "Inactive item JA203004 should be visible"
    assert len(items) == 4, f"Expected 4 total items, found {len(items)}"


@pytest.mark.e2e
def test_status_filter_default_is_active_only(page, live_server):
    """Test that 'Active Only' is the default filter selection"""
    # Add test data with both active and inactive items
    test_items = [
        {
            "ja_id": "JA204001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "500",
            "width": "12",
            "location": "Storage A",
            "notes": "Active steel rod",
            "active": True
        },
        {
            "ja_id": "JA204002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "1000",
            "width": "500",
            "thickness": "3",
            "location": "Storage B",
            "notes": "Inactive aluminum sheet",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Verify 'Active Only' is selected by default
    status_filter = page.locator("#status-filter")
    expect(status_filter).to_have_value("active")

    # Verify the selected option text
    selected_option = status_filter.locator("option:checked")
    expect(selected_option).to_have_text("Active Only")
