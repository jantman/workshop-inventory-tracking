"""
E2E Tests for Move Items Functionality

Tests the complete workflow for batch moving inventory items including:
- Barcode scanning simulation (keyboard wedge)
- Move queue management
- Validation workflow
- Actual move execution
- Error handling and edge cases
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


class MoveItemsPage(BasePage):
    """Page object for inventory move interface"""
    
    def navigate(self):
        """Navigate to move items page"""
        self.page.goto(f"{self.base_url}/inventory/move")
        self.page.wait_for_load_state("networkidle")
    
    def simulate_barcode_scan(self, barcode_text):
        """Simulate barcode scanner input (keyboard wedge + Enter)"""
        barcode_input = self.page.locator("#barcode-input")
        # Clear the input first
        barcode_input.fill("")
        # Focus the input to make sure events fire
        barcode_input.focus()
        # Type the barcode text character by character (more realistic)
        barcode_input.type(barcode_text)
        # Press Enter to trigger processing
        barcode_input.press("Enter")
        # Wait for JavaScript processing and any AJAX calls
        self.page.wait_for_timeout(500)
    
    def enable_manual_entry_mode(self):
        """Enable manual entry mode for testing"""
        self.page.locator("#manual-entry-mode").check()
    
    def get_queue_count(self):
        """Get the number of items in the move queue"""
        count_text = self.page.locator("#queue-count").inner_text()
        return int(count_text.split()[0])
    
    def get_status_text(self):
        """Get the current status text"""
        return self.page.locator("#status-text").inner_text()
    
    def click_validate_moves(self):
        """Click the validate & preview button"""
        self.page.locator("#validate-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def click_execute_moves(self):
        """Click the execute moves button"""
        self.page.locator("#execute-moves-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def click_clear_queue(self):
        """Click the clear queue button"""
        self.page.locator("#clear-queue-btn").click()
    
    def click_clear_all(self):
        """Click the clear all button"""
        self.page.locator("#clear-all-btn").click()
    
    def assert_queue_item_visible(self, ja_id, new_location):
        """Assert that a specific move is visible in the queue"""
        queue_table = self.page.locator("#queue-items")
        expect(queue_table.locator(f"text={ja_id}")).to_be_visible()
        expect(queue_table.locator(f"text={new_location}")).to_be_visible()
    
    def assert_validation_section_visible(self):
        """Assert that the validation section is displayed"""
        expect(self.page.locator("#validation-section")).to_be_visible()
    
    def assert_success_message(self, message_text=None):
        """Assert success message is shown"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        if message_text:
            expect(alert).to_contain_text(message_text)


@pytest.mark.e2e
def test_move_page_loads(page, live_server):
    """Test that move page loads with correct elements"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Should show the move interface
    expect(page.locator("h2")).to_contain_text("Batch Move Items")
    expect(page.locator("#barcode-input")).to_be_visible()
    expect(page.locator("#move-queue-empty")).to_be_visible()
    
    # Buttons should be in correct initial state
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#execute-moves-btn")).to_be_disabled()
    expect(page.locator("#clear-queue-btn")).to_be_disabled()


@pytest.mark.e2e
def test_single_item_move_workflow(page, live_server):
    """Test moving a single item through complete workflow"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # First add an item to move
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a hardcoded test JA ID
    ja_id_to_use = "JA000101"
    
    add_page.fill_basic_item_data(
        ja_id_to_use,
        "Bar",
        "Round", 
        "Carbon Steel"
    )
    add_page.fill_dimensions(
        length='1000',
        width='25'
    )
    add_page.fill_location_and_notes(
        location="Shop A",
        notes="Test item for moving"
    )
    add_page.submit_form()
    
    # Wait for success message or page redirect
    page.wait_for_timeout(1000)
    
    # Verify the item was actually added by checking for success message
    success_alert = page.locator(".alert-success").first
    if success_alert.is_visible():
        print(f"✓ Item {ja_id_to_use} successfully added")
    else:
        # Check if there's an error
        error_alert = page.locator(".alert-danger").first
        if error_alert.is_visible():
            print(f"✗ Error adding item: {error_alert.inner_text()}")
    
    # Navigate to inventory list to ensure item is in the database
    page.goto(f"{live_server.url}/inventory")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)  # Extra wait for data loading
    
    # Verify the item appears in the inventory list
    if page.locator(f"text={ja_id_to_use}").count() > 0:
        print(f"✓ Item {ja_id_to_use} confirmed in inventory list")
    else:
        print(f"✗ Item {ja_id_to_use} NOT found in inventory list")
    
    # Use the JA ID we assigned
    ja_id = ja_id_to_use
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Extra wait to ensure the move interface is fully loaded
    page.wait_for_timeout(1000)
    
    print(f"About to scan JA ID: {ja_id}")
    
    # Test full automated barcode scanning flow (no manual entry mode)
    # Simulate scanning the item JA ID
    move_page.simulate_barcode_scan(ja_id)
    
    # First check for any alert messages (this should have been our first diagnostic step)
    error_alerts = page.locator(".alert-danger")
    if error_alerts.count() > 0:
        for i in range(error_alerts.count()):
            error_text = error_alerts.nth(i).inner_text()
            print(f"Error message {i+1}: {error_text}")
            
    success_alerts = page.locator(".alert-success") 
    if success_alerts.count() > 0:
        for i in range(success_alerts.count()):
            success_text = success_alerts.nth(i).inner_text()
            print(f"Success message {i+1}: {success_text}")
    
    # Debug: Check what's in the input field and current status
    input_value = page.locator("#barcode-input").input_value()
    current_status = move_page.get_status_text()
    print(f"Input field value after scan: '{input_value}'")
    print(f"Status after scanning {ja_id}: {current_status}")
    
    # Should now expect location
    assert "location" in move_page.get_status_text().lower()
    
    # Simulate scanning new location
    move_page.simulate_barcode_scan("Shop B")
    
    # Should show item in queue
    assert move_page.get_queue_count() == 1
    move_page.assert_queue_item_visible(ja_id, "Shop B")
    
    # Simulate >>DONE<< to finish scanning
    move_page.simulate_barcode_scan(">>DONE<<")
    
    # Validate moves should be enabled
    expect(page.locator("#validate-btn")).to_be_enabled()
    
    # Click validate
    move_page.click_validate_moves()
    move_page.assert_validation_section_visible()
    
    # Execute moves should now be enabled
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    
    # Execute the moves
    move_page.click_execute_moves()
    
    # Should show success message
    move_page.assert_success_message("successfully")


@pytest.mark.e2e 
def test_multiple_items_move_workflow(page, live_server):
    """Test moving multiple items in one batch"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add two test items
    add_page = AddItemPage(page, live_server.url)
    ja_ids = []
    
    for i in range(2):
        add_page.navigate()
        # Use a unique hardcoded test JA ID
        ja_id_to_use = f"JA00010{i+2}"
        
        add_page.fill_basic_item_data(
            ja_id_to_use,
            "Bar",
            "Round",
            "Carbon Steel"
        )
        add_page.fill_dimensions(
            length='1000', 
            width='25'
        )
        add_page.fill_location_and_notes(
            location="Shop A",
            notes=f"Test item {i+1} for batch moving"
        )
        add_page.submit_form()
        ja_ids.append(ja_id_to_use)
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Move both items to different locations
    locations = ["Shop B", "Shop C"]
    
    for i, ja_id in enumerate(ja_ids):
        # Scan JA ID
        move_page.simulate_barcode_scan(ja_id)
        
        # Scan new location
        move_page.simulate_barcode_scan(locations[i])
        
        # Verify it's added to queue
        move_page.assert_queue_item_visible(ja_id, locations[i])
    
    # Should have 2 items in queue
    assert move_page.get_queue_count() == 2
    
    # Complete and execute moves
    move_page.simulate_barcode_scan(">>DONE<<")
    move_page.click_validate_moves()
    move_page.click_execute_moves()
    
    # Should show success
    move_page.assert_success_message("successfully")


@pytest.mark.e2e
def test_move_nonexistent_item_error(page, live_server):
    """Test error handling when trying to move non-existent item"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Try to scan non-existent JA ID
    move_page.simulate_barcode_scan("JA999999")
    
    # Should accept the JA ID initially (validation happens later)
    assert "location" in move_page.get_status_text().lower()
    
    # Scan location
    move_page.simulate_barcode_scan("Test Location")
    
    # Should now have 1 item in queue
    assert move_page.get_queue_count() == 1
    
    # Complete scanning and validate - this is where the error should appear
    move_page.simulate_barcode_scan(">>DONE<<")
    move_page.click_validate_moves()
    
    # Wait for validation to complete
    page.wait_for_timeout(2000)
    
    # Check that the item shows as not found in the queue
    queue_table = page.locator("#queue-items")
    expect(queue_table.locator("text=not_found").or_(queue_table.locator("text=error"))).to_be_visible()


@pytest.mark.e2e
def test_clear_queue_functionality(page, live_server):
    """Test clearing the move queue"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add test item  
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a hardcoded test JA ID
    ja_id_to_use = "JA000105"
    
    add_page.fill_basic_item_data(
        ja_id_to_use,
        "Bar",
        "Round",
        "Aluminum"
    )
    add_page.fill_dimensions(
        length='2000',
        width='50'
    )
    add_page.fill_location_and_notes(
        location="Rack 1",
        notes="Test item for queue clearing"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to move page and add item to queue
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    move_page.simulate_barcode_scan(ja_id)
    move_page.simulate_barcode_scan("Rack 2")
    
    # Verify item in queue
    assert move_page.get_queue_count() == 1
    
    # Clear the queue
    move_page.click_clear_queue()
    
    # Queue should be empty
    assert move_page.get_queue_count() == 0
    expect(page.locator("#move-queue-empty")).to_be_visible()
    
    # Buttons should be disabled again
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#execute-moves-btn")).to_be_disabled()


@pytest.mark.e2e
def test_move_item_with_original_thread_regression_test(page, live_server):
    """Regression test: Move item with original_thread value to prevent AttributeError bug"""
    from sqlalchemy.orm import sessionmaker
    from app.database import InventoryItem
    
    # Add item directly to database with original_thread value (simulates legacy/migrated data)
    ja_id = "JA000107"
    Session = sessionmaker(bind=live_server.engine)
    session = Session()
    
    try:
        db_item = InventoryItem(
            ja_id=ja_id,
            item_type="Bar",
            shape="Round", 
            material="Steel",
            length=1500.0,
            width=30.0,
            location="Storage Room A",
            notes="Regression test item with original_thread",
            original_thread="5/16-18",  # This would have caused the AttributeError bug
            active=True
        )
        
        session.add(db_item)
        session.commit()
        print(f"✅ Added regression test item {ja_id} with original_thread='5/16-18'")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error adding regression test item: {e}")
        raise
    finally:
        session.close()
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # This workflow would have failed with "AttributeError: 'str' object has no attribute 'to_dict'"
    # before the bug was fixed
    move_page.simulate_barcode_scan(ja_id)
    
    # Check for any error alerts that would indicate the bug is still present
    error_alerts = page.locator(".alert-danger")
    if error_alerts.count() > 0:
        for i in range(error_alerts.count()):
            error_text = error_alerts.nth(i).inner_text()
            print(f"❌ Error alert {i+1}: {error_text}")
            # If we see an AttributeError about to_dict, the bug is not fixed
            if "AttributeError" in error_text and "to_dict" in error_text:
                pytest.fail(f"Bug regression detected: {error_text}")
    
    # Scan new location
    move_page.simulate_barcode_scan("Storage Room B")
    
    # Should have successfully added item to queue
    assert move_page.get_queue_count() == 1
    move_page.assert_queue_item_visible(ja_id, "Storage Room B")
    
    # Complete the move workflow
    move_page.simulate_barcode_scan(">>DONE<<")
    move_page.click_validate_moves()
    move_page.click_execute_moves()
    
    # Should complete successfully without AttributeError
    move_page.assert_success_message("successfully")
    print(f"✅ Regression test passed: Item with original_thread moved successfully")


