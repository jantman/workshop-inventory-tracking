"""
Basic E2E Tests for Shorten Items Interface

Tests the essential UI components and data loss prevention measures for shorten functionality.
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


@pytest.mark.e2e
def test_shorten_interface_loads_correctly(page, live_server):
    """Test that shorten interface loads with proper elements and safety features"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Should show the shorten interface
    expect(page.locator("h2")).to_contain_text("Shorten Items")
    
    # Essential elements should be present
    expect(page.locator("#source-ja-id")).to_be_visible()
    expect(page.locator("#load-item-btn")).to_be_visible()
    expect(page.locator("#scan-ja-id-btn")).to_be_visible()
    
    # Safety features: key sections should be hidden initially
    expect(page.locator("#item-details")).not_to_be_visible()
    expect(page.locator("#shortening-section")).not_to_be_visible()
    expect(page.locator("#new-item-section")).not_to_be_visible()
    expect(page.locator("#summary-section")).not_to_be_visible()
    
    # Clear form option should be available
    expect(page.locator("#clear-form-btn")).to_be_visible()
    
    # Navigation should be available (escape route)
    expect(page.locator('a:has-text("View All Items")')).to_be_visible()


@pytest.mark.e2e
def test_shorten_input_validation_present(page, live_server):
    """Test that input validation elements are present"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # JA ID input should have proper validation
    ja_id_input = page.locator("#source-ja-id")
    expect(ja_id_input).to_have_attribute("pattern", "JA\\d{6}")
    expect(ja_id_input).to_have_attribute("required")
    expect(ja_id_input).to_have_attribute("title")
    
    # Should have placeholder with example
    placeholder = ja_id_input.get_attribute("placeholder")
    assert "JA" in placeholder and "000001" in placeholder
    
    # Invalid feedback should be present
    expect(page.locator(".invalid-feedback")).to_be_visible()


@pytest.mark.e2e
def test_shorten_safety_workflow_structure(page, live_server):
    """Test that safety workflow structure is in place"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Form should have CSRF protection
    expect(page.locator('input[name="csrf_token"]')).to_be_visible()
    
    # Should have proper form structure
    form = page.locator("#shorten-form")
    expect(form).to_be_visible()
    expect(form).to_have_attribute("method", "POST")
    
    # Important warning about item validation should be present
    warning_section = page.locator(".alert-warning")
    expect(warning_section).to_exist()  # Should exist even if hidden


@pytest.mark.e2e
def test_shorten_item_loading_workflow(page, live_server):
    """Test basic item loading workflow"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Try to load non-existent item (should handle gracefully)
    page.locator("#source-ja-id").fill("JA999999")
    page.locator("#load-item-btn").click()
    page.wait_for_load_state("networkidle")
    
    # Should show not found message (safety feature)
    expect(page.locator("#item-not-found")).to_be_visible()
    
    # Should NOT show other sections (safety feature)
    expect(page.locator("#shortening-section")).not_to_be_visible()
    expect(page.locator("#new-item-section")).not_to_be_visible()


@pytest.mark.e2e 
def test_shorten_length_validation_structure(page, live_server):
    """Test that length validation structure exists"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Length validation section should exist
    expect(page.locator("#length-validation")).to_exist()
    expect(page.locator("#length-validation-alert")).to_exist()
    
    # New length input should have proper attributes
    new_length_input = page.locator("#new-length")
    expect(new_length_input).to_have_attribute("pattern")
    expect(new_length_input).to_have_attribute("required") 
    expect(new_length_input).to_have_attribute("title")
    
    # Cut loss input should be optional but validated
    cut_loss_input = page.locator("#cut-loss")
    expect(cut_loss_input).to_have_attribute("pattern")


@pytest.mark.e2e
def test_shorten_confirmation_workflow_exists(page, live_server):
    """Test that confirmation workflow exists (critical safety feature)"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Confirmation checkbox should exist
    confirm_checkbox = page.locator("#confirm-operation")
    expect(confirm_checkbox).to_exist()
    expect(confirm_checkbox).to_have_attribute("type", "checkbox")
    expect(confirm_checkbox).to_have_attribute("required", "")
    
    # Confirmation label should be strong/emphatic
    confirm_label = page.locator('label[for="confirm-operation"]')
    expect(confirm_label).to_be_visible()
    label_text = confirm_label.inner_text()
    assert "confirm" in label_text.lower()
    assert "operation" in label_text.lower()


@pytest.mark.e2e
def test_shorten_operation_summary_structure(page, live_server):
    """Test that operation summary structure exists"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Summary section should exist
    expect(page.locator("#summary-section")).to_exist()
    
    # Key summary fields should exist
    expect(page.locator("#summary-original-id")).to_exist()
    expect(page.locator("#summary-original-length")).to_exist()
    expect(page.locator("#summary-new-length")).to_exist()
    expect(page.locator("#summary-removed-length")).to_exist()
    expect(page.locator("#summary-new-id")).to_exist()


@pytest.mark.e2e
def test_shorten_ja_id_generation_safety(page, live_server):
    """Test JA ID generation safety features"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # New JA ID should be readonly (prevent manual tampering)
    new_ja_id_input = page.locator("#new-ja-id")
    expect(new_ja_id_input).to_have_attribute("readonly", "")
    expect(new_ja_id_input).to_have_attribute("pattern", "JA\\d{6}")
    expect(new_ja_id_input).to_have_attribute("required")
    
    # Generate button should be present
    expect(page.locator("#generate-ja-id-btn")).to_be_visible()


@pytest.mark.e2e
def test_shorten_clear_form_functionality(page, live_server):
    """Test clear form functionality works"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Add some data to form
    page.locator("#source-ja-id").fill("JA123456")
    
    # Click clear form  
    page.locator("#clear-form-btn").click()
    
    # Form should be cleared
    expect(page.locator("#source-ja-id")).to_have_value("")


@pytest.mark.e2e
def test_shorten_proper_navigation_available(page, live_server):
    """Test that proper navigation is available"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Should have navigation back to main inventory
    expect(page.locator('a:has-text("View All Items")')).to_be_visible()
    
    # Should be able to navigate back  
    back_link = page.locator('a:has-text("View All Items")')
    href = back_link.get_attribute("href")
    assert "/inventory" in href