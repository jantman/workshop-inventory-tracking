"""
E2E Tests for Move Items with original_thread Values

Tests that would have caught the original_thread.to_dict() bug by creating
items with non-null original_thread values and attempting to move them.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage
from sqlalchemy.orm import sessionmaker
from app.database import InventoryItem


class MoveItemsPage(BasePage):
    """Page object for inventory move interface"""
    
    def navigate(self):
        """Navigate to move items page"""
        self.page.goto(f"{self.base_url}/inventory/move")
        self.page.wait_for_load_state("networkidle")
    
    def simulate_barcode_scan(self, barcode_text):
        """Simulate barcode scanner input (keyboard wedge + Enter)"""
        barcode_input = self.page.locator("#barcode-input")
        barcode_input.fill("")
        barcode_input.focus()
        barcode_input.type(barcode_text)
        barcode_input.press("Enter")
        self.page.wait_for_timeout(500)
    
    def get_queue_count(self):
        """Get the number of items in the move queue"""
        count_text = self.page.locator("#queue-count").inner_text()
        return int(count_text.split()[0])
    
    def click_validate_moves(self):
        """Click the validate & preview button"""
        self.page.locator("#validate-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def click_execute_moves(self):
        """Click the execute moves button"""
        self.page.locator("#execute-moves-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def assert_success_message(self, message_text=None):
        """Assert success message is shown"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        if message_text:
            expect(alert).to_contain_text(message_text)


def add_item_with_original_thread(live_server, ja_id, original_thread_value):
    """Helper function to add an item with original_thread directly to database"""
    # Get database session
    Session = sessionmaker(bind=live_server.engine)
    session = Session()
    
    try:
        # Create database item directly with original_thread value
        db_item = InventoryItem(
            ja_id=ja_id,
            item_type="Bar",
            shape="Round",
            material="Steel",
            length=1000.0,
            width=25.0,
                location="M12-L",
            notes="Test item with original_thread",
            original_thread=original_thread_value,  # This is the key field
            active=True
        )
        
        session.add(db_item)
        session.commit()
        print(f"✅ Added test item {ja_id} with original_thread='{original_thread_value}'")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error adding test item: {e}")
        raise
    finally:
        session.close()


@pytest.mark.e2e
def test_move_item_with_original_thread_string(page, live_server):
    """Test moving an item that has original_thread as string (would trigger the bug)"""
    # Add a test item with original_thread value directly to database
    ja_id = "JA000201"
    add_item_with_original_thread(live_server, ja_id, "1/4-20")
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Test the move workflow that would have triggered the bug
    move_page.simulate_barcode_scan(ja_id)
    
    # Check for any error alerts immediately
    error_alerts = page.locator(".alert-danger")
    if error_alerts.count() > 0:
        for i in range(error_alerts.count()):
            error_text = error_alerts.nth(i).inner_text()
            print(f"Error message {i+1}: {error_text}")
    
    # Scan new location
    move_page.simulate_barcode_scan("M13-M")

    # Complete scanning to finalize the move (required in new sub-location workflow)
    move_page.simulate_barcode_scan(">>DONE<<")

    # Should have item in queue without error (after finalization)
    assert move_page.get_queue_count() == 1
    
    # Validate moves
    move_page.click_validate_moves()
    
    # Execute moves - this would have failed with the bug
    move_page.click_execute_moves()
    
    # Should show success (confirming bug is fixed)
    move_page.assert_success_message("successfully")


@pytest.mark.e2e
def test_move_item_with_original_thread_none(page, live_server):
    """Test moving an item that has original_thread as None (should work in both cases)"""
    # Add a test item with original_thread=None
    ja_id = "JA000202"
    add_item_with_original_thread(live_server, ja_id, None)
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Test the move workflow
    move_page.simulate_barcode_scan(ja_id)
    move_page.simulate_barcode_scan("M14-N")

    # Complete workflow to finalize the move (required in new sub-location workflow)
    move_page.simulate_barcode_scan(">>DONE<<")

    # Should have item in queue (after finalization)
    assert move_page.get_queue_count() == 1
    move_page.click_validate_moves()
    move_page.click_execute_moves()
    
    # Should show success
    move_page.assert_success_message("successfully")


@pytest.mark.e2e
def test_move_multiple_items_with_mixed_original_thread(page, live_server):
    """Test moving multiple items with different original_thread values"""
    # Add test items with different original_thread values
    items = [
        ("JA000203", "M10x1.5"),  # String value
        ("JA000204", None),       # None value
        ("JA000205", "3/8-16"),   # Another string value
    ]
    
    for ja_id, original_thread in items:
        add_item_with_original_thread(live_server, ja_id, original_thread)
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()

    # Move all items to the same location (new workflow: each JA ID finalizes previous move)
    for i, (ja_id, _) in enumerate(items):
        move_page.simulate_barcode_scan(ja_id)
        if i > 0:
            # Wait for finalization to complete (async operation with API call)
            page.wait_for_timeout(500)
            # Verify previous item was added to queue
            assert move_page.get_queue_count() == i
        move_page.simulate_barcode_scan("M15-O")

    # Complete scanning to finalize the last move
    move_page.simulate_barcode_scan(">>DONE<<")
    # Wait for finalization to complete (async operation with API call)
    page.wait_for_timeout(500)

    # Should have all items in queue
    assert move_page.get_queue_count() == 3
    move_page.click_validate_moves()
    move_page.click_execute_moves()
    
    # Should show success for all items
    move_page.assert_success_message("successfully")


@pytest.mark.e2e
def test_move_item_with_original_thread_empty_string(page, live_server):
    """Test moving an item that has original_thread as empty string"""
    # Add a test item with original_thread as empty string
    ja_id = "JA000206"
    add_item_with_original_thread(live_server, ja_id, "")
    
    # Navigate to move page
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Test the move workflow
    move_page.simulate_barcode_scan(ja_id)
    move_page.simulate_barcode_scan("M16-P")

    # Complete workflow to finalize the move (required in new sub-location workflow)
    move_page.simulate_barcode_scan(">>DONE<<")

    # Should have item in queue (after finalization)
    assert move_page.get_queue_count() == 1
    move_page.click_validate_moves()
    move_page.click_execute_moves()
    
    # Should show success
    move_page.assert_success_message("successfully")