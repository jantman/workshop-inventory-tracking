"""
E2E Tests for Shorten Items Functionality

Tests the complete workflow for shortening inventory items using keep-same-ID approach:
- Item loading and validation
- Length calculations and validation
- Keep-same-ID shortening workflow
- Confirmation workflow
- Actual shortening execution with history preservation
- Error handling and edge cases
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


class ShortenItemsPage(BasePage):
    """Page object for inventory shorten interface"""
    
    def navigate(self):
        """Navigate to shorten items page"""
        self.page.goto(f"{self.base_url}/inventory/shorten")
        self.page.wait_for_load_state("networkidle")
    
    def enter_source_ja_id(self, ja_id):
        """Enter source JA ID"""
        self.page.locator("#source-ja-id").fill(ja_id)
    
    def click_load_item(self):
        """Click the load item button"""
        self.page.locator("#load-item-btn").click()
        self.page.wait_for_load_state("networkidle")
    
    def simulate_ja_id_scan(self, ja_id):
        """Simulate barcode scanner input for JA ID"""
        ja_input = self.page.locator("#source-ja-id")
        ja_input.fill("")
        ja_input.type(ja_id)
        ja_input.press("Enter")
        self.page.wait_for_timeout(200)
        # Auto-load should happen
        self.page.wait_for_load_state("networkidle")
    
    def enter_new_length(self, length):
        """Enter new length for shortened item"""
        self.page.locator("#new-length").fill(str(length))
    
    
    def enter_shortening_notes(self, notes):
        """Enter shortening operation notes"""
        self.page.locator("#shortening-notes").fill(notes)
    
    
    def check_confirm_operation(self):
        """Check the confirm operation checkbox"""
        self.page.locator("#confirm-operation").check()
    
    def click_execute_shortening(self):
        """Click execute shortening button"""
        self.page.locator('button:has-text("Execute Shortening")').click()
        self.page.wait_for_load_state("networkidle")
    
    def assert_item_details_visible(self):
        """Assert item details section is visible"""
        expect(self.page.locator("#item-details")).to_be_visible()
    
    def assert_item_not_found(self):
        """Assert item not found message is visible"""
        expect(self.page.locator("#item-not-found")).to_be_visible()
    
    def assert_shortening_section_visible(self):
        """Assert shortening details section is visible"""
        expect(self.page.locator("#shortening-section")).to_be_visible()
    
    def assert_notes_section_visible(self):
        """Assert shortening notes section is visible"""
        expect(self.page.locator("#notes-section")).to_be_visible()
    
    def assert_summary_section_visible(self):
        """Assert operation summary section is visible"""
        expect(self.page.locator("#summary-section")).to_be_visible()
    
    def get_current_length(self):
        """Get the current length from item details"""
        return self.page.locator("#current-length").inner_text()
    
    
    def get_summary_current_length(self):
        """Get current length from summary"""
        return self.page.locator("#summary-current-length").inner_text()
    
    def get_summary_ja_id(self):
        """Get JA ID from summary"""
        return self.page.locator("#summary-ja-id").inner_text()
    
    def get_summary_new_length(self):
        """Get new length from summary"""
        return self.page.locator("#summary-new-length").inner_text()
    
    def get_summary_removed_length(self):
        """Get removed length from summary"""
        return self.page.locator("#summary-removed-length").inner_text()
    
    def assert_length_validation_error(self):
        """Assert that length validation shows an error"""
        expect(self.page.locator("#length-validation")).to_be_visible()
        expect(self.page.locator("#length-validation-alert.alert-danger")).to_be_visible()
    
    def assert_success_message(self, message_text=None):
        """Assert success message is shown"""
        alert = self.page.locator(".alert-success").first
        expect(alert).to_be_visible()
        if message_text:
            expect(alert).to_contain_text(message_text)


@pytest.mark.e2e
def test_shorten_page_loads(page, live_server):
    """Test that shorten page loads with correct elements"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Should show the shorten interface
    expect(page.locator("h2")).to_contain_text("Shorten Items")
    expect(page.locator("#source-ja-id")).to_be_visible()
    expect(page.locator("#load-item-btn")).to_be_visible()
    
    # Sections should be hidden initially
    expect(page.locator("#item-details")).not_to_be_visible()
    expect(page.locator("#shortening-section")).not_to_be_visible()
    expect(page.locator("#notes-section")).not_to_be_visible()
    expect(page.locator("#summary-section")).not_to_be_visible()


@pytest.mark.e2e
def test_load_item_for_shortening(page, live_server):
    """Test loading an existing item for shortening"""
    from tests.e2e.pages.add_item_page import AddItemPage
    
    # First add a bar item that can be shortened
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
        length='1200',  # 100 feet, plenty to shorten
        width='25'
    )
    add_page.fill_location_and_notes(
        location="Stock Room",
        notes="Test bar for shortening"
    )
    add_page.submit_form()
    
    # Use the JA ID we assigned
    ja_id = ja_id_to_use
    
    # Navigate to shorten page
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Load the item
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    
    # Should show item details
    shorten_page.assert_item_details_visible()
    shorten_page.assert_shortening_section_visible()
    
    # Should display correct current length
    current_length = shorten_page.get_current_length()
    assert "1200" in current_length or "100" in current_length  # Could display as decimal


@pytest.mark.e2e
def test_load_nonexistent_item(page, live_server):
    """Test loading a non-existent item shows error"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Try to load non-existent item
    shorten_page.enter_source_ja_id("JA999999")
    shorten_page.click_load_item()
    
    # Should show not found message
    shorten_page.assert_item_not_found()
    
    # Should not show other sections
    expect(page.locator("#shortening-section")).not_to_be_visible()
    expect(page.locator("#notes-section")).not_to_be_visible()


@pytest.mark.e2e
def test_barcode_scan_workflow(page, live_server):
    """Test loading item via barcode scan simulation"""
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
        length='480',  # 40 feet
        width='12'
    )
    add_page.fill_location_and_notes(
        location="Rack A",
        notes="Test rod for scanning"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to shorten page
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Simulate barcode scan
    shorten_page.simulate_ja_id_scan(ja_id)
    
    # Should auto-load the item
    shorten_page.assert_item_details_visible()
    shorten_page.assert_shortening_section_visible()


@pytest.mark.e2e
def test_complete_shortening_workflow(page, live_server):
    """Test complete shortening workflow from start to finish"""
    # Add test item directly to storage (bypassing UI to focus on shortening workflow)
    ja_id_to_use = "JA000001"
    
    from app.models import Item, ItemType, ItemShape, Dimensions
    from decimal import Decimal
    
    test_item = Item(
        ja_id=ja_id_to_use,
        item_type=ItemType.BAR,
        shape=ItemShape.RECTANGULAR,
        material="Steel",
        dimensions=Dimensions(length=Decimal('600'), width=Decimal('50'), thickness=Decimal('1')),  # 50 feet x 50" x 1"
        location="Storage Bay 1",
        notes="Test bar for complete shortening workflow",
        active=True
    )
    
    # Add item directly to test server storage
    live_server.add_test_data([test_item])
    ja_id = ja_id_to_use
    
    # Navigate to shorten page and load item
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    
    # Wait for item to load and sections to become visible
    shorten_page.assert_item_details_visible()
    shorten_page.assert_shortening_section_visible()
    
    # Enter shortening details
    shorten_page.enter_new_length("240")  # 20 feet (shortened by 30 feet)
    
    # Should show notes section after entering new length
    shorten_page.assert_notes_section_visible()
    
    # Enter shortening notes
    shorten_page.enter_shortening_notes("Cut with bandsaw for test project")
    
    # Should show summary section
    shorten_page.assert_summary_section_visible()
    
    # Verify summary information
    ja_id_summary = shorten_page.get_summary_ja_id()
    current_length = shorten_page.get_summary_current_length()
    new_length = shorten_page.get_summary_new_length()
    removed_length = shorten_page.get_summary_removed_length()
    
    assert ja_id == ja_id_summary  # Same JA ID should be preserved
    assert "600" in current_length or "50" in current_length
    assert "240" in new_length or "20" in new_length
    assert "360" in removed_length or "30" in removed_length  # 30 feet removed
    
    # Confirm and execute
    shorten_page.check_confirm_operation()
    
    # Submit the form (this will use the actual form submission)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    
    # Should show success message with preserved JA ID (check for any alert first)
    # Wait a moment for any message to appear
    page.wait_for_timeout(2000)
    
    # Check if there are any alerts (success or error)
    success_alert = page.locator(".alert-success").first
    error_alert = page.locator(".alert-danger,.alert-error").first
    
    if success_alert.is_visible():
        # Success - check for expected text
        message_text = success_alert.inner_text()
        assert "History preserved" in message_text or "successfully shortened" in message_text, f"Unexpected success message: {message_text}"
    elif error_alert.is_visible():
        # Error - fail with the error message
        error_text = error_alert.inner_text()
        assert False, f"Shortening operation failed with error: {error_text}"
    else:
        # No alert found
        assert False, "No success or error message found after shortening operation"


@pytest.mark.e2e
def test_invalid_length_validation(page, live_server):
    """Test validation when new length is invalid"""
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
        material="Brass"
    )
    add_page.fill_dimensions(
        length='120',  # 10 feet
        width='19'
    )
    add_page.fill_location_and_notes(
        location="Shelf 1",
        notes="Test item for length validation"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to shorten page and load item
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    
    # Try to enter new length longer than original
    shorten_page.enter_new_length("180")  # 15 feet, longer than 10 feet original
    
    # Should show validation error
    page.wait_for_timeout(1000)  # Wait for validation
    shorten_page.assert_length_validation_error()


@pytest.mark.e2e
def test_zero_or_negative_length_validation(page, live_server):
    """Test validation when new length is zero or negative"""
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
        material="Copper"
    )
    add_page.fill_dimensions(
        length='240',  # 20 feet
        width='38'
    )
    add_page.fill_location_and_notes(
        location="Bin 5",
        notes="Test rod for zero length validation"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to shorten page and load item
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    
    # Try to enter zero length
    shorten_page.enter_new_length("0")
    
    # Should show validation error
    page.wait_for_timeout(1000)
    shorten_page.assert_length_validation_error()
    
    # Try negative length
    shorten_page.enter_new_length("-5")
    page.wait_for_timeout(1000)
    shorten_page.assert_length_validation_error()


@pytest.mark.e2e
def test_keep_same_id_workflow(page, live_server):
    """Test that shortening preserves the same JA ID"""
    # Add test item directly to storage (bypassing UI to focus on shortening workflow)
    ja_id_to_use = "JA000001"
    
    from app.models import Item, ItemType, ItemShape, Dimensions
    from decimal import Decimal
    
    test_item = Item(
        ja_id=ja_id_to_use,
        item_type=ItemType.PLATE,
        shape=ItemShape.RECTANGULAR,
        material="Steel",
        dimensions=Dimensions(length=Decimal('240'), width=Decimal('120'), thickness=Decimal('0.25')),  # 20 feet x 10 feet x 1/4"
        location="Table A",
        notes="Test plate for keep-same-ID workflow",
        active=True
    )
    
    # Add item directly to test server storage
    live_server.add_test_data([test_item])
    ja_id = ja_id_to_use
    
    # Navigate to shorten page and load item
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    
    # Enter valid new length
    shorten_page.enter_new_length("120")
    
    # Should show notes section
    shorten_page.assert_notes_section_visible()
    
    # Verify summary shows same JA ID
    shorten_page.assert_summary_section_visible()
    ja_id_summary = shorten_page.get_summary_ja_id()
    assert ja_id == ja_id_summary  # Same JA ID should be preserved throughout


@pytest.mark.e2e
def test_form_reset_functionality(page, live_server):
    """Test form reset clears all data"""
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
        material="Stainless Steel"
    )
    add_page.fill_dimensions(
        length='360',
        width='25'
    )
    add_page.fill_location_and_notes(
        location="Rack B",
        notes="Test item for form reset"
    )
    add_page.submit_form()
    ja_id = ja_id_to_use
    
    # Navigate to shorten page and fill out form
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    shorten_page.enter_source_ja_id(ja_id)
    shorten_page.click_load_item()
    shorten_page.enter_new_length("180")
    shorten_page.enter_shortening_notes("Test notes")
    
    # Should have data in form
    shorten_page.assert_item_details_visible()
    shorten_page.assert_shortening_section_visible()
    
    # Click clear form button
    page.locator("#clear-form-btn").click()
    
    # Form should be reset
    expect(page.locator("#source-ja-id")).to_have_value("")
    expect(page.locator("#item-details")).not_to_be_visible()
    expect(page.locator("#shortening-section")).not_to_be_visible()
    expect(page.locator("#notes-section")).not_to_be_visible()

