"""
Basic E2E Tests for Move Items Interface

Tests the essential UI components and data loss prevention measures for move functionality.
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


@pytest.mark.e2e
def test_move_interface_loads_correctly(page, live_server):
    """Test that move interface loads with proper elements and safety features"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Should show the move interface
    expect(page.locator("h2")).to_contain_text("Batch Move Items")
    
    # Essential elements should be present
    expect(page.locator("#barcode-input")).to_be_visible()
    expect(page.locator("#move-queue-empty")).to_be_visible()
    expect(page.locator("#scanner-status")).to_be_visible()
    expect(page.locator("#input-status")).to_be_visible()
    
    # Safety features: buttons should be disabled initially (prevent accidental execution)
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#execute-moves-btn")).to_be_disabled()
    expect(page.locator("#clear-queue-btn")).to_be_disabled()
    
    # Safety features: clear buttons should be available
    expect(page.locator("#clear-all-btn")).to_be_enabled()
    
    # Manual entry mode option should be available (backup for scanner issues)
    expect(page.locator("#manual-entry-mode")).to_be_visible()
    
    # Instructions should be clearly visible
    expect(page.locator("text=Scan or type JA ID")).to_be_visible()
    expect(page.locator("text=DONE").first).to_be_visible()


@pytest.mark.e2e
def test_move_interface_workflow_protection(page, live_server):
    """Test that move interface enforces safe workflow"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Should show proper initial state
    status_text = page.locator("#status-text").inner_text().lower()
    assert "ready" in status_text or "first" in status_text
    
    # Queue should be empty initially
    expect(page.locator("#move-queue-empty")).to_be_visible()
    queue_count = page.locator("#queue-count").inner_text()
    assert "0 items" in queue_count
    
    # Navigation should be available (escape route)
    assert page.locator('a:has-text("View All Items")').count() > 0, "Should have View All Items link"
    expect(page.locator('button:has-text("Clear All")')).to_be_enabled()
    
    # Form should have proper structure for data integrity
    expect(page.locator('form#batch-move-form')).to_be_visible()
    assert page.locator('input[name="csrf_token"]').count() > 0, "Should have CSRF token"


@pytest.mark.e2e
def test_move_manual_entry_mode_toggle(page, live_server):
    """Test manual entry mode toggle functionality"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Manual entry mode should be off by default
    manual_checkbox = page.locator("#manual-entry-mode")
    expect(manual_checkbox).not_to_be_checked()
    
    # Should be able to toggle manual entry mode
    manual_checkbox.check()
    expect(manual_checkbox).to_be_checked()
    
    # Scanner status should update
    page.wait_for_timeout(500)  # Allow JavaScript to update
    
    manual_checkbox.uncheck()
    expect(manual_checkbox).not_to_be_checked()


@pytest.mark.e2e
def test_move_input_field_focuses_properly(page, live_server):
    """Test that barcode input field is ready for scanning"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Barcode input should be focused for immediate scanning
    barcode_input = page.locator("#barcode-input")
    expect(barcode_input).to_be_focused()
    
    # Input should have proper attributes
    expect(barcode_input).to_have_attribute("autocomplete", "off")
    placeholder = barcode_input.get_attribute("placeholder")
    assert placeholder is not None and len(placeholder) > 0
    
    # Should be able to type in the field
    barcode_input.type("test")
    expect(barcode_input).to_have_value("test")


@pytest.mark.e2e  
def test_move_clear_all_functionality(page, live_server):
    """Test clear all button resets form state"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Add some text to input
    page.locator("#barcode-input").fill("test input")
    
    # Click clear all
    page.locator("#clear-all-btn").click()
    
    # Input should be cleared
    expect(page.locator("#barcode-input")).to_have_value("")
    
    # Should still be in ready state
    status_text = page.locator("#status-text").inner_text().lower()
    assert "ready" in status_text or "first" in status_text


@pytest.mark.e2e
def test_move_validation_workflow_exists(page, live_server):
    """Test that validation workflow is present (safety requirement)"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Validation section should exist (but be hidden initially)
    expect(page.locator("#validation-section")).not_to_be_visible()
    
    # Validate button should exist with proper text
    validate_btn = page.locator("#validate-btn")
    expect(validate_btn).to_contain_text("Validate")
    expect(validate_btn).to_contain_text("Preview")
    
    # Execute button should exist with clear labeling
    execute_btn = page.locator("#execute-moves-btn")  
    expect(execute_btn).to_contain_text("Execute")
    expect(execute_btn).to_contain_text("Moves")
    
    # Cancel option should be available
    expect(page.locator('a:has-text("Cancel")')).to_be_visible()


@pytest.mark.e2e
def test_move_instructions_are_clear(page, live_server):
    """Test that move instructions are clearly displayed (prevent user errors)"""
    move_page = MoveItemsPage(page, live_server.url)
    move_page.navigate()
    
    # Instructions should be visible and clear
    instructions = page.locator(".form-text").first
    expect(instructions).to_be_visible()
    
    instruction_text = instructions.inner_text().lower()
    assert "scan" in instruction_text or "type" in instruction_text
    assert "ja id" in instruction_text
    assert "location" in instruction_text
    assert "done" in instruction_text
    
    # Important safety info should be displayed
    safety_info = page.locator('text="Validate & Preview"')
    expect(safety_info).to_be_visible()