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
        # Type the barcode and press Enter (simulating scanner)
        barcode_input.type(barcode_text)
        barcode_input.press("Enter")
        # Small delay to allow JavaScript processing
        self.page.wait_for_timeout(200)
    
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
    # Use a test JA ID
    ja_id_to_use = "JA000001"
    
    add_page.fill_basic_item_data(
        ja_id=ja_id_to_use,
        item_type="Bar",
        shape="Round", 
        material="Steel"
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
    
    # Use the JA ID we assigned
    ja_id = ja_id_to_use
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Simulate scanning the item JA ID
    move_page.simulate_barcode_scan(ja_id)
    
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
    move_page.assert_success_message("successfully moved")


@pytest.mark.e2e 
def test_multiple_items_move_workflow(page, live_server):
    """Test moving multiple items in one batch"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add two test items
    add_page = AddItemPage(page, live_server.url)
    ja_ids = []
    
    for i in range(2):
        add_page.navigate()
        # Generate JA ID first
        ja_id_to_use = f"JA00020{i+1}"
        
        add_page.fill_basic_item_data(
            ja_id=ja_id_to_use,
            item_type="Bar",
            shape="Round",
            material="Steel"
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
    move_page.assert_success_message("successfully moved")


@pytest.mark.e2e
def test_move_nonexistent_item_error(page, live_server):
    """Test error handling when trying to move non-existent item"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Try to scan non-existent JA ID
    move_page.simulate_barcode_scan("JA999999")
    
    # Should show error status or alert
    # Wait for any error messages to appear
    page.wait_for_timeout(1000)
    
    # Check for error indicators
    error_alert = page.locator(".alert-danger").first
    if error_alert.is_visible():
        expect(error_alert).to_contain_text("not found")
    else:
        # Check status text for error indication
        status = move_page.get_status_text().lower()
        assert "error" in status or "not found" in status or "invalid" in status


@pytest.mark.e2e
def test_manual_entry_mode(page, live_server):
    """Test manual entry mode instead of barcode scanning"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a test JA ID
    ja_id_to_use = "JA000001"
    
    add_page.fill_basic_item_data(
        ja_id=ja_id_to_use,
        item_type="Bar",
        shape="Round",
        material="Steel"
    )
    add_page.fill_dimensions(
        length='500',
        width='12'
    )
    add_page.fill_location_and_notes(
        location="Storage A",
        notes="Test item for manual entry"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Enable manual entry mode
    move_page.enable_manual_entry_mode()
    
    # Type JA ID and press Enter manually
    barcode_input = page.locator("#barcode-input")
    barcode_input.fill(ja_id)
    barcode_input.press("Enter")
    page.wait_for_timeout(200)
    
    # Type location and press Enter
    barcode_input.fill("Storage B")
    barcode_input.press("Enter")
    page.wait_for_timeout(200)
    
    # Should show item in queue
    assert move_page.get_queue_count() == 1
    move_page.assert_queue_item_visible(ja_id, "Storage B")


@pytest.mark.e2e
def test_clear_queue_functionality(page, live_server):
    """Test clearing the move queue"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add test item  
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a test JA ID
    ja_id_to_use = "JA000001"
    
    add_page.fill_basic_item_data(
        ja_id=ja_id_to_use,
        item_type="Bar",
        shape="Round",
        material="Aluminum"
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
def test_clear_all_functionality(page, live_server):
    """Test clearing all entries and resetting the form"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a test JA ID
    ja_id_to_use = "JA000001"
    
    add_page.fill_basic_item_data(
        ja_id=ja_id_to_use,
        item_type="Plate",
        shape="Rectangular",
        material="Steel"
    )
    add_page.fill_dimensions(
        length='500',
        width='300'
    )
    add_page.fill_location_and_notes(
        location="Table 1",
        notes="Test item for clear all"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to move page and start adding item
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    move_page.simulate_barcode_scan(ja_id)
    # Don't complete the location, test clearing mid-process
    
    # Clear all
    move_page.click_clear_all()
    
    # Everything should be reset
    assert move_page.get_queue_count() == 0
    assert "ready to scan first ja id" in move_page.get_status_text().lower()
    expect(page.locator("#barcode-input")).to_have_value("")


@pytest.mark.e2e 
def test_move_validation_before_execution(page, live_server):
    """Test that validation happens before moves can be executed"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # Add test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    # Use a test JA ID
    ja_id_to_use = "JA000001"
    
    add_page.fill_basic_item_data(
        ja_id=ja_id_to_use,
        item_type="Rod",
        shape="Round",
        material="Brass"
    )
    add_page.fill_dimensions(
        length='750',
        width='20'
    )
    add_page.fill_location_and_notes(
        location="Bin A",
        notes="Test item for validation"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to move page and queue item
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    move_page.simulate_barcode_scan(ja_id)
    move_page.simulate_barcode_scan("Bin B")
    move_page.simulate_barcode_scan(">>DONE<<")
    
    # Validate button should be enabled, execute should be disabled
    expect(page.locator("#validate-btn")).to_be_enabled()
    expect(page.locator("#execute-moves-btn")).to_be_disabled()
    
    # After validation, execute should be enabled
    move_page.click_validate_moves()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    
    # Should show validation results
    move_page.assert_validation_section_visible()