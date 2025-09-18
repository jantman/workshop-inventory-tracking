"""
E2E Tests for Edit Item Deactivation Bug

Tests to reproduce and verify the bug where items can't be deactivated 
through the Edit Item form.
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.add_item_page import AddItemPage
from playwright.sync_api import expect
from app.database import InventoryItem


@pytest.mark.e2e
def test_deactivate_item_via_edit_form(page, live_server):
    """Test deactivating an item through the Edit Item form"""
    # First add a test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA200001",
        "item_type": "Bar",
        "shape": "Round", 
        "material": "Steel",
        "length": "10.0",
        "width": "0.5",
        "location": "Test Rack",
        "notes": "Test item for deactivation"
    }
    
    # Fill and submit the test item
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], 
                                 test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Verify item was created and is active in database
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=live_server.engine)
    session = Session()
    
    try:
        db_item = session.query(InventoryItem).filter_by(ja_id="JA200001").first()
        assert db_item is not None, "Item was not created in database"
        assert db_item.active is True, "Item should be active after creation"
        
        # Navigate to inventory list and verify item appears
        list_page = InventoryListPage(page, live_server.url)
        list_page.navigate()
        list_page.wait_for_items_loaded()
        
        # Verify item appears in the list (active items should be visible)
        items = list_page.get_inventory_items()
        item_found = any(item['ja_id'] == 'JA200001' for item in items)
        assert item_found, "Active item should be visible in inventory list"
        
        # Navigate to edit page
        edit_link = page.locator(f'a[href="/inventory/edit/JA200001"]')
        expect(edit_link).to_be_visible()
        edit_link.click()
        
        # Verify we're on the edit page
        expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA200001')
        
        # Verify the Active checkbox is currently checked
        active_checkbox = page.locator('#active')
        expect(active_checkbox).to_be_visible()
        expect(active_checkbox).to_be_checked()
        
        # Uncheck the Active checkbox to deactivate the item
        active_checkbox.uncheck()
        
        # Verify checkbox is now unchecked
        expect(active_checkbox).not_to_be_checked()
        
        # Submit the form
        submit_button = page.locator('button[type="submit"]')
        submit_button.click()
        
        # Verify redirect to inventory list
        expect(page).to_have_url(f'{live_server.url}/inventory')
        
        # Verify success message
        success_alert = page.locator('.alert-success')
        expect(success_alert).to_contain_text('Item updated successfully!')
        
        # Check database to verify item is actually deactivated
        # Close current session and create a fresh one to avoid transaction isolation issues
        session.close()
        fresh_session = Session()
        
        try:
            db_item_refreshed = fresh_session.query(InventoryItem).filter_by(ja_id="JA200001").first()
            assert db_item_refreshed is not None, "Item should still exist in database"
            assert db_item_refreshed.active is False, "Item should be deactivated in database after form submission"
        finally:
            fresh_session.close()
        
    except:
        session.close()
        raise