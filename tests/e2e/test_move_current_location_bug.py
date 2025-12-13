"""
E2E Test for Move Form Current Location Bug (Issue #3)

This test reproduces the bug where after scanning an item into the Move Queue,
the current location always shows as "Unknown" instead of the actual current location.

The test should initially fail (demonstrating the bug) and then pass after the fix.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.add_item_page import AddItemPage


class MoveCurrentLocationPage(BasePage):
    """Page object for testing move current location functionality"""
    
    def navigate_to_move(self):
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
    
    def click_validate_moves(self):
        """Click the validate & preview button"""
        self.page.locator("#validate-btn").click()
        self.page.wait_for_load_state("networkidle")
        # Wait for validation to complete
        self.page.wait_for_timeout(2000)
    
    def get_current_location_from_queue(self, ja_id):
        """Get the current location displayed for a specific JA ID in the queue"""
        # Find the row containing the JA ID and get the current location cell
        queue_table = self.page.locator("#queue-items")
        # Find the row with the JA ID
        ja_id_row = queue_table.locator("tr").filter(has_text=ja_id)
        # Get the second cell (current location column)
        current_location_cell = ja_id_row.locator("td").nth(1)
        return current_location_cell.inner_text().strip()


@pytest.mark.e2e
def test_move_current_location_shows_unknown_bug(page, live_server):
    """
    Test that reproduces the bug where current location shows as 'Unknown'
    instead of the actual location of the item.
    
    This test should initially FAIL (demonstrating the bug exists),
    then PASS after the bug is fixed.
    """
    # Step 1: Create a test item with a known location
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_ja_id = "JA000505"  # Using a unique JA ID for this test
    expected_location = "M10-J"
    
    add_page.fill_basic_item_data(
        test_ja_id,
        "Bar",
        "Round", 
        "Aluminum"
    )
    add_page.fill_dimensions(
        length='500',
        width='12'
    )
    add_page.fill_location_and_notes(
        location=expected_location,
        notes="Test item for current location bug test"
    )
    add_page.submit_form()
    
    # Wait for the item to be created
    page.wait_for_timeout(1000)
    
    # Verify the item was created successfully
    success_alert = page.locator(".alert-success").first
    expect(success_alert).to_be_visible()
    
    # Step 2: Navigate to move page
    move_page = MoveCurrentLocationPage(page, live_server.url)
    move_page.navigate_to_move()
    
    # Step 3: Scan the item JA ID and new location
    move_page.simulate_barcode_scan(test_ja_id)
    page.wait_for_timeout(500)

    new_location = "M11-K"
    move_page.simulate_barcode_scan(new_location)
    page.wait_for_timeout(500)

    # Finalize the move (required in new sub-location workflow)
    move_page.simulate_barcode_scan(">>DONE<<")
    page.wait_for_timeout(500)

    # Step 4: Verify the item appears in the queue
    queue_table = page.locator("#queue-items")
    expect(queue_table.locator(f"text={test_ja_id}")).to_be_visible()
    expect(queue_table.locator(f"text={new_location}")).to_be_visible()
    
    # Step 5: Check current location BEFORE validation
    # This is where the bug occurs - it should show the actual location but shows "Unknown"
    current_location_before_validation = move_page.get_current_location_from_queue(test_ja_id)
    
    # BUG: This assertion should FAIL initially, demonstrating the bug
    # The current location shows "Unknown" instead of the actual location
    print(f"Current location before validation: '{current_location_before_validation}'")
    print(f"Expected location: '{expected_location}'")
    
    # This assertion will fail initially (demonstrating the bug)
    # After the fix, it should pass
    assert current_location_before_validation != "Unknown", (
        f"BUG REPRODUCED: Current location shows 'Unknown' instead of '{expected_location}'. "
        f"The current location should be populated immediately when the item is added to the queue, "
        f"not just after validation."
    )
    
    # Additional verification: The current location should match the expected location
    assert current_location_before_validation == expected_location, (
        f"Current location should be '{expected_location}' but got '{current_location_before_validation}'"
    )


