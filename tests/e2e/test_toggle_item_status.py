"""
E2E Tests for toggleItemStatus Function (Bug 3)

Tests to reproduce bug where the "Activate Item" dropdown action
shows JavaScript error: "toggleItemStatus is not defined"
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.inventory_list_page import InventoryListPage
from app.database import InventoryItem
from sqlalchemy.orm import sessionmaker


@pytest.mark.e2e
def test_toggle_item_status_function_exists(page, live_server):
    """Test that toggleItemStatus function is available globally (Bug 3)

    Expected to FAIL initially: The toggleItemStatus function should be
    defined globally but is currently undefined, causing JavaScript errors.
    """
    # Add inactive test item
    test_item = {
        "ja_id": "JA302001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": 12.0,
        "width": 0.5,
        "location": "Storage A",
        "notes": "Inactive item for testing toggleItemStatus",
        "active": False
    }

    live_server.add_test_data([test_item])

    # Navigate to inventory list with inactive filter
    page.goto(f'{live_server.url}/inventory')

    # Change status filter to "Inactive Only"
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')

    # Wait for items to load
    page.wait_for_timeout(1000)

    # Verify toggleItemStatus function is defined as a global function
    # After fix, this should return true
    is_function = page.evaluate('typeof window.toggleItemStatus === "function"')
    assert is_function, "toggleItemStatus should be defined as a global function"


@pytest.mark.e2e
def test_activate_inactive_item_via_dropdown(page, live_server):
    """Test activating an inactive item via the dropdown action (Bug 3)

    Expected to FAIL initially: Clicking "Activate" shows console error
    "toggleItemStatus is not defined" and item is not activated.
    """
    # Add inactive test item
    test_item = {
        "ja_id": "JA302002",
        "item_type": "Plate",
        "shape": "Flat",
        "material": "Stainless Steel",
        "length": 24.0,
        "width": 12.0,
        "thickness": 0.125,
        "location": "Storage B",
        "notes": "Inactive plate to test activation",
        "active": False
    }

    live_server.add_test_data([test_item])

    # Verify item is inactive in database
    Session = sessionmaker(bind=live_server.engine)
    session = Session()

    try:
        db_item = session.query(InventoryItem).filter_by(ja_id="JA302002").first()
        assert db_item is not None, "Test item should exist"
        assert db_item.active is False, "Test item should be inactive"
    finally:
        session.close()

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Change status filter to "Inactive Only"
    status_filter = page.locator('#status-filter')
    status_filter.select_option('inactive')

    # Wait for items to load
    list_page.wait_for_items_loaded()

    # Verify inactive item appears in list
    items = list_page.get_inventory_items()
    item_found = any(item['ja_id'] == 'JA302002' for item in items)
    assert item_found, "Inactive item JA302002 should be visible in filtered list"

    # Find the actions dropdown button for this item
    # The dropdown toggle is in the actions column
    actions_dropdown = page.locator(f'tr:has-text("JA302002") .dropdown-toggle').first()
    expect(actions_dropdown).to_be_visible()

    # Click to open dropdown
    actions_dropdown.click()

    # Wait for dropdown menu to be visible
    dropdown_menu = page.locator(f'tr:has-text("JA302002") .dropdown-menu').first()
    expect(dropdown_menu).to_be_visible()

    # Find the "Activate" menu item (has eye icon for inactive items)
    activate_link = dropdown_menu.locator('a:has-text("Activate")').first()
    expect(activate_link).to_be_visible()

    # Set up a console message listener to catch JavaScript errors
    console_errors = []

    def handle_console(msg):
        if msg.type == 'error':
            console_errors.append(msg.text)

    page.on('console', handle_console)

    # Set up dialog handler for confirmation (click OK)
    page.on('dialog', lambda dialog: dialog.accept())

    # Click the Activate link
    activate_link.click()

    # Wait a moment for any JavaScript to execute and page to reload
    page.wait_for_timeout(1000)

    # After fix, there should be no JavaScript errors
    assert not console_errors, f"No JavaScript errors should occur, but got: {console_errors}"

    # After fix, page should reload to show the item as active
    # Verify we're back on the inventory page
    expect(page).to_have_url(f'{live_server.url}/inventory')

    # Verify item is now active in database
    fresh_session = Session()
    try:
        db_item_refreshed = fresh_session.query(InventoryItem).filter_by(ja_id="JA302002").first()
        assert db_item_refreshed is not None, "Item should still exist"
        assert db_item_refreshed.active is True, "Item should now be active"
    finally:
        fresh_session.close()


@pytest.mark.e2e
def test_deactivate_active_item_via_dropdown(page, live_server):
    """Test deactivating an active item via the dropdown action

    This ensures the toggleItemStatus function works in both directions.
    """
    # Add active test item
    test_item = {
        "ja_id": "JA302003",
        "item_type": "Bar",
        "shape": "Hex",
        "material": "Aluminum",
        "length": 36.0,
        "width": 1.5,
        "location": "Storage C",
        "notes": "Active item to test deactivation",
        "active": True
    }

    live_server.add_test_data([test_item])

    # Navigate to inventory list (defaults to active items)
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Verify active item appears in list
    items = list_page.get_inventory_items()
    item_found = any(item['ja_id'] == 'JA302003' for item in items)
    assert item_found, "Active item JA302003 should be visible in list"

    # Find the actions dropdown button for this item
    actions_dropdown = page.locator(f'tr:has-text("JA302003") .dropdown-toggle').first()
    expect(actions_dropdown).to_be_visible()
    actions_dropdown.click()

    # Find the "Deactivate" menu item
    dropdown_menu = page.locator(f'tr:has-text("JA302003") .dropdown-menu').first()
    deactivate_link = dropdown_menu.locator('a:has-text("Deactivate")').first()
    expect(deactivate_link).to_be_visible()

    # Set up dialog handler for confirmation
    page.on('dialog', lambda dialog: dialog.accept())

    # Click the Deactivate link
    deactivate_link.click()

    # Wait for page reload
    page.wait_for_timeout(1000)

    # Verify we're back on inventory page
    expect(page).to_have_url(f'{live_server.url}/inventory')

    # Verify item is now inactive in database
    Session = sessionmaker(bind=live_server.engine)
    session = Session()
    try:
        db_item = session.query(InventoryItem).filter_by(ja_id="JA302003").first()
        assert db_item is not None, "Item should still exist"
        assert db_item.active is False, "Item should now be inactive"
    finally:
        session.close()
