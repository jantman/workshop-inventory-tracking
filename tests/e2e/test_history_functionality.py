"""
E2E Tests for Item History Functionality

Tests for the complete history viewing functionality across all interfaces:
- History button visibility and functionality in inventory list
- History button in search results
- History button in item details modal
- History button in edit form
- History modal display and content
- Error handling for non-existent items
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.add_item_page import AddItemPage
from playwright.sync_api import expect


@pytest.mark.e2e
def test_history_button_visibility_inventory_list(page, live_server):
    """Test that history button is visible in inventory list"""
    # First add a test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "24",
        "width": "1",
        "location": "Workshop",
        "notes": "Test item for history functionality"
    }
    
    # Add the item
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    
    # Find the history button for our item
    history_button = page.locator(f'button[onclick*="showItemHistory(\'JA301001\')"]')
    expect(history_button).to_be_visible()
    expect(history_button).to_have_attribute('title', 'View History')
    
    # Verify the button has the correct icon
    history_icon = history_button.locator('i.bi-clock-history')
    expect(history_icon).to_be_visible()


@pytest.mark.e2e
def test_history_modal_functionality_from_inventory_list(page, live_server):
    """Test opening history modal from inventory list"""
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301002",
        "item_type": "Plate",
        "shape": "Rectangular",
        "material": "Aluminum",
        "length": "12",
        "width": "6",
        "thickness": "0.25",
        "location": "Storage A",
        "notes": "Test plate for history modal"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    page.fill("#thickness", test_item["thickness"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    
    # Click the history button
    history_button = page.locator(f'button[onclick*="showItemHistory(\'JA301002\')"]')
    expect(history_button).to_be_visible()
    history_button.click()
    
    # Wait for history modal to appear
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    
    # Verify modal title
    modal_title = page.locator('#item-history-modal-label')
    expect(modal_title).to_contain_text('Item History - JA301002')
    
    # Verify modal contains item information (check for item characteristics)
    modal_body = page.locator('#history-modal-body')
    expect(modal_body).to_contain_text('Aluminum')
    
    # Verify summary section shows correct counts
    expect(modal_body).to_contain_text('Total Versions')
    expect(modal_body).to_contain_text('Active Items')
    
    # Close modal
    close_button = page.locator('#item-history-modal .btn-close')
    close_button.click()
    expect(history_modal).not_to_be_visible()


@pytest.mark.e2e
def test_history_functionality_in_search_results(page, live_server):
    """Test history functionality in search results page"""
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301003",
        "item_type": "Plate",
        "shape": "Rectangular",
        "material": "Aluminum",
        "length": "12",
        "width": "6",
        "thickness": "0.25",
        "location": "Storage A",
        "notes": "Test plate for search history"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    page.fill("#thickness", test_item["thickness"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Wait a moment for submission to complete
    page.wait_for_timeout(2000)
    
    # Navigate to search page
    page.goto(f'{live_server.url}/inventory/search')
    
    # Search for our item
    page.fill('#ja_id', 'JA301003')
    page.click('button[type="submit"]')
    
    # Wait for search results
    page.wait_for_selector('#results-table-container', state='visible')
    
    # Find view details button in search results
    view_button = page.locator('button[onclick*="viewItemDetails(\'JA301003\')"]')
    expect(view_button).to_be_visible()
    
    # Click to open details modal
    view_button.click()
    
    # Wait for details modal
    details_modal = page.locator('#item-details-modal')
    expect(details_modal).to_be_visible()
    
    # Find and click history button in modal footer
    history_btn_in_modal = page.locator('#view-history-from-details-btn')
    expect(history_btn_in_modal).to_be_visible()
    history_btn_in_modal.click()
    
    # Verify history modal opens
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    expect(history_modal).to_contain_text('Item History - JA301003')


@pytest.mark.e2e  
def test_history_button_in_item_details_modal(page, live_server):
    """Test history button functionality in item details modal"""
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301004",
        "item_type": "Sheet",
        "shape": "Rectangular", 
        "material": "Stainless Steel",
        "length": "24",
        "width": "12",
        "thickness": "0.125",
        "location": "Storage C",
        "notes": "Test sheet for details modal history"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    page.fill("#thickness", test_item["thickness"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    
    # Click view details button
    view_button = page.locator(f'button[onclick*="showItemDetails(\'JA301004\')"]')
    expect(view_button).to_be_visible()
    view_button.click()
    
    # Wait for details modal
    details_modal = page.locator('#item-details-modal')
    expect(details_modal).to_be_visible()
    
    # Verify history button exists in modal footer
    history_button = page.locator('#view-history-from-details-btn')
    expect(history_button).to_be_visible()
    expect(history_button).to_contain_text('View History')
    
    # Click history button
    history_button.click()
    
    # Verify details modal closes and history modal opens
    expect(details_modal).not_to_be_visible()
    
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    expect(history_modal).to_contain_text('Item History - JA301004')


@pytest.mark.e2e
def test_history_button_in_edit_form(page, live_server):
    """Test history button functionality in edit form"""
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301005",
        "item_type": "Tube",
        "shape": "Round",
        "material": "Copper",
        "length": "36",
        "width": "2",
        "wall_thickness": "0.125",
        "location": "Workshop C",
        "notes": "Test tube for edit form history"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    page.fill("#wall_thickness", test_item["wall_thickness"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to edit form
    page.goto(f'{live_server.url}/inventory/edit/JA301005')
    
    # Verify page loaded
    expect(page).to_have_title('Edit JA301005 - Workshop Inventory')
    
    # Find history button in header
    history_button = page.locator(f'button[onclick*="showItemHistory(\'JA301005\')"]')
    expect(history_button).to_be_visible()
    expect(history_button).to_contain_text('View History')
    
    # Click history button
    history_button.click()
    
    # Verify history modal opens
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    expect(history_modal).to_contain_text('Item History - JA301005')
    
    # Verify edit link in history modal points back to edit form
    edit_link = page.locator('#edit-item-from-history-link')
    expect(edit_link).to_have_attribute('href', '/inventory/edit/JA301005')


@pytest.mark.e2e
def test_history_error_handling_nonexistent_item(page, live_server):
    """Test error handling when viewing history of non-existent item"""
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Manually call showItemHistory with non-existent ID
    page.evaluate('showItemHistory("JA999999")')
    
    # Wait for history modal to appear
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    
    # Verify error message in modal
    modal_body = page.locator('#history-modal-body')
    expect(modal_body).to_contain_text('Error Loading History')


@pytest.mark.e2e
def test_history_modal_content_and_formatting(page, live_server):
    """Test that history modal displays content with proper formatting"""
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301006",
        "item_type": "Bar",
        "shape": "Square",
        "material": "Steel",
        "length": "10",
        "width": "1.5",
        "location": "Test Location",
        "notes": "Test bar for content formatting"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list and open history
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    
    history_button = page.locator(f'button[onclick*="showItemHistory(\'JA301006\')"]')
    history_button.click()
    
    # Wait for history modal
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    
    modal_body = page.locator('#history-modal-body')
    
    # Verify timeline structure exists
    timeline = modal_body.locator('.history-timeline')
    expect(timeline).to_be_visible()
    
    # Verify at least one timeline item exists
    timeline_item = modal_body.locator('.timeline-item')
    expect(timeline_item).to_be_visible()
    
    # Verify active item badge
    active_badge = modal_body.locator('.badge.bg-success')
    expect(active_badge).to_contain_text('Active')
    
    # Verify dimensions are displayed
    expect(modal_body).to_contain_text('L: 10"')
    expect(modal_body).to_contain_text('W: 1.5"')


@pytest.mark.e2e
def test_history_modal_responsive_design(page, live_server):
    """Test that history modal works on mobile viewport"""
    # Set mobile viewport
    page.set_viewport_size({"width": 375, "height": 667})
    
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA301007",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Aluminum",
        "length": "100",
        "width": "0.125",
        "location": "Mobile Test",
        "notes": "Test bar for mobile responsiveness"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    
    # Open history modal
    history_button = page.locator(f'button[onclick*="showItemHistory(\'JA301007\')"]')
    history_button.click()
    
    # Verify modal is visible and responsive
    history_modal = page.locator('#item-history-modal')
    expect(history_modal).to_be_visible()
    
    # Verify modal content is still accessible on mobile
    modal_body = page.locator('#history-modal-body')
    expect(modal_body).to_be_visible()
    
    # Verify timeline is still functional
    timeline = modal_body.locator('.history-timeline')
    expect(timeline).to_be_visible()