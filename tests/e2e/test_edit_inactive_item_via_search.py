"""
E2E Tests for Editing Inactive Items (Bugs 1 & 2)

Tests to reproduce bugs where inactive items cannot be edited:
- Bug 1: Search box returns "Item not found" for inactive items
- Bug 2: Manual URL navigation returns "Item not found" for inactive items
"""

import pytest
from playwright.sync_api import expect
from app.database import InventoryItem
from sqlalchemy.orm import sessionmaker


@pytest.mark.e2e
def test_edit_inactive_item_via_search_box(page, live_server):
    """Test editing inactive item via search box (Bug 1)

    Expected to FAIL initially: Search box should find inactive items
    but currently returns "Item not found" error.
    """
    # Add test data with one active and one inactive item
    test_items = [
        {
            "ja_id": "JA300001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": 12.0,
            "width": 0.5,
            "location": "Storage A",
            "notes": "Active test item",
            "active": True
        },
        {
            "ja_id": "JA300002",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": 24.0,
            "width": 0.75,
            "location": "Storage B",
            "notes": "Inactive test item",
            "active": False
        }
    ]

    live_server.add_test_data(test_items)

    # Navigate to inventory list page
    page.goto(f'{live_server.url}/inventory')

    # Verify page loaded
    expect(page).to_have_url(f'{live_server.url}/inventory')

    # Locate the JA ID search input in top-right navigation
    ja_id_input = page.locator('#ja-id-lookup')
    expect(ja_id_input).to_be_visible()

    # Type inactive item JA ID and press Enter
    ja_id_input.fill('JA300002')
    ja_id_input.press('Enter')

    # Expected: Should navigate to edit page for JA300002
    # Actual (current bug): Shows "Item not found" flash message

    # After fix, this should work:
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA300002')

    # Verify edit form shows the inactive item
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA300002')

    # Verify the active checkbox is unchecked (item is inactive)
    active_checkbox = page.locator('#active')
    expect(active_checkbox).not_to_be_checked()


@pytest.mark.e2e
def test_edit_inactive_item_via_manual_url(page, live_server):
    """Test editing inactive item via manual URL navigation (Bug 2)

    Expected to FAIL initially: Manual URL should load edit page for
    inactive items but currently redirects with "Item not found" error.
    """
    # Add test data with inactive item
    test_item = {
        "ja_id": "JA301001",
        "item_type": "Plate",
        "shape": "Flat",
        "material": "Aluminum",
        "length": 36.0,
        "width": 12.0,
        "thickness": 0.25,
        "location": "Storage C",
        "notes": "Inactive plate for testing",
        "active": False
    }

    live_server.add_test_data([test_item])

    # Verify item is in database and inactive
    Session = sessionmaker(bind=live_server.engine)
    session = Session()

    try:
        db_item = session.query(InventoryItem).filter_by(ja_id="JA301001").first()
        assert db_item is not None, "Test item should exist in database"
        assert db_item.active is False, "Test item should be inactive"
    finally:
        session.close()

    # Navigate directly to edit URL for inactive item
    page.goto(f'{live_server.url}/inventory/edit/JA301001')

    # Expected: Should show edit form for JA301001
    # Actual (current bug): Redirects to inventory list with "Item not found" flash message

    # After fix, should be on edit page:
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA301001')

    # Verify edit form loads with correct data
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA301001')

    # Verify the active checkbox is unchecked
    active_checkbox = page.locator('#active')
    expect(active_checkbox).not_to_be_checked()

    # Verify material field shows correct value
    material_input = page.locator('#material')
    expect(material_input).to_have_value('Aluminum')

    # Verify location field shows correct value
    location_input = page.locator('#location')
    expect(location_input).to_have_value('Storage C')


@pytest.mark.e2e
def test_active_item_still_works_via_search(page, live_server):
    """Verify that active items can still be found via search box

    This test ensures our fix doesn't break the existing functionality
    for active items.
    """
    # Add active test item
    test_item = {
        "ja_id": "JA302001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": 18.0,
        "width": 1.0,
        "location": "Storage D",
        "notes": "Active item for regression test",
        "active": True
    }

    live_server.add_test_data([test_item])

    # Navigate to inventory list
    page.goto(f'{live_server.url}/inventory')

    # Use search box to find active item
    ja_id_input = page.locator('#ja-id-lookup')
    ja_id_input.fill('JA302001')
    ja_id_input.press('Enter')

    # Should navigate to edit page successfully
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA302001')

    # Verify edit form loads
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA302001')

    # Verify the active checkbox is checked
    active_checkbox = page.locator('#active')
    expect(active_checkbox).to_be_checked()
