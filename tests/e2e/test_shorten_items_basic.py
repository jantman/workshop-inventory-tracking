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
    
    # Clear form option should be available
    expect(page.locator("#clear-form-btn")).to_be_visible()
    
    # Navigation should be available (escape route)
    assert page.locator('a:has-text("View All Items")').count() > 0, "Should have navigation back to inventory"


@pytest.mark.e2e
def test_shorten_input_validation_present(page, live_server):
    """Test that input validation elements are present"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # JA ID input should have basic validation
    ja_id_input = page.locator("#source-ja-id")
    expect(ja_id_input).to_have_attribute("pattern", "JA\\d{6}")
    expect(ja_id_input).to_have_attribute("required", "")
    
    # Should have placeholder with example
    placeholder = ja_id_input.get_attribute("placeholder")
    assert "JA" in placeholder and "000001" in placeholder


@pytest.mark.e2e
def test_shorten_safety_workflow_structure(page, live_server):
    """Test that safety workflow structure is in place"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Form should have CSRF protection
    assert page.locator('input[name="csrf_token"]').count() > 0, "Should have CSRF token"
    
    # Should have proper form structure
    form = page.locator("#shorten-form")
    expect(form).to_be_visible()
    expect(form).to_have_attribute("method", "POST")


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


@pytest.mark.e2e 
def test_shorten_length_validation_structure(page, live_server):
    """Test that length validation structure exists"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Length validation section should exist
    assert page.locator("#length-validation").count() > 0, "Should have length validation section"
    
    # New length input should exist
    assert page.locator("#new-length").count() > 0, "Should have new length input"


@pytest.mark.e2e
def test_shorten_confirmation_workflow_exists(page, live_server):
    """Test that confirmation workflow exists (critical safety feature)"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Confirmation checkbox should exist
    confirm_checkbox = page.locator("#confirm-operation")
    assert confirm_checkbox.count() > 0, "Should have confirmation checkbox"
    
    # Confirmation label should exist (may be hidden until item loaded)
    confirm_label = page.locator('label[for="confirm-operation"]')
    assert confirm_label.count() > 0, "Should have confirmation label"


@pytest.mark.e2e
def test_shorten_operation_summary_structure(page, live_server):
    """Test that operation summary structure exists"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Summary section should exist
    assert page.locator("#summary-section").count() > 0, "Should have summary section"


@pytest.mark.e2e
def test_shorten_keep_same_id_safety(page, live_server):
    """Test keep-same-ID safety features in new shortening workflow"""
    shorten_page = ShortenItemsPage(page, live_server.url)
    shorten_page.navigate()
    
    # Should NOT have new JA ID input (keep-same-ID approach)
    new_ja_id_input = page.locator("#new-ja-id")
    expect(new_ja_id_input).not_to_be_visible()
    
    # Should NOT have generate button (no new IDs generated)
    generate_btn = page.locator("#generate-ja-id-btn")
    expect(generate_btn).not_to_be_visible()
    
    # Should have source JA ID input for item identification
    source_ja_id_input = page.locator("#source-ja-id")
    expect(source_ja_id_input).to_be_visible()
    expect(source_ja_id_input).to_have_attribute("pattern", "JA\\d{6}")


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
    assert page.locator('a:has-text("View All Items")').count() > 0, "Should have View All Items link"
    
    # Should be able to navigate back  
    back_link = page.locator('a:has-text("View All Items")').first
    href = back_link.get_attribute("href")
    assert "/inventory" in href