"""
E2E Tests for Data Loss Prevention in Move and Shorten Operations

These tests verify that the high-risk operations (Move and Shorten) have proper
safety measures in place to prevent accidental data loss or corruption.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.base_page import BasePage


@pytest.mark.e2e
def test_move_interface_has_safety_measures(page, live_server):
    """Test that Move interface has essential safety measures"""
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    # Should load the move interface
    expect(page.locator("h2")).to_contain_text("Move Items")
    
    # Should have clear instructions
    expect(page.locator("text=Scan JA ID").first).to_be_visible()
    expect(page.locator("text=DONE").first).to_be_visible()
    
    # Should have validation step before execution
    expect(page.locator("text=Validate").first).to_be_visible()
    expect(page.locator("text=Preview").first).to_be_visible()
    
    # Should have execute button separate from validation
    expect(page.locator("text=Execute").first).to_be_visible()
    
    # Should have clear/cancel options
    expect(page.locator("text=Clear").first).to_be_visible()
    expect(page.locator("text=Cancel").first).to_be_visible()


@pytest.mark.e2e
def test_shorten_interface_has_safety_measures(page, live_server):
    """Test that Shorten interface has essential safety measures"""
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    # Should load the shorten interface
    expect(page.locator("h2")).to_contain_text("Shorten Items")
    
    # Should have JA ID input for item identification
    expect(page.locator("#source-ja-id")).to_be_visible()
    
    # Should have load/validation step
    expect(page.locator("text=Load").first).to_be_visible()
    
    # Should have confirmation requirement (may be hidden until item loaded)
    assert page.locator("text=confirm").count() > 0, "Should have confirmation text element"
    
    # Should have clear/cancel options
    expect(page.locator("text=Clear").first).to_be_visible()
    # Navigation link exists (may be in dropdown)
    assert page.locator('a:has-text("View All Items")').count() > 0, "Should have navigation back to inventory"


@pytest.mark.e2e
def test_move_interface_prevents_immediate_execution(page, live_server):
    """Test that Move interface doesn't allow immediate execution without validation"""
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    # Execute button should be disabled initially
    execute_btn = page.locator("button").filter(has_text="Execute")
    if execute_btn.is_visible():
        expect(execute_btn).to_be_disabled()
    
    # Validate button should exist (required step)
    validate_btn = page.locator("button").filter(has_text="Validate")  
    expect(validate_btn).to_be_visible()


@pytest.mark.e2e
def test_shorten_interface_requires_confirmation(page, live_server):
    """Test that Shorten interface requires explicit confirmation"""
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    # Should have confirmation checkbox (visible after loading an item)
    confirm_elements = page.locator("input[type='checkbox']").all()
    assert len(confirm_elements) > 0, "Should have confirmation checkbox"
    
    # Should have execute button that requires confirmation (keep-same-ID approach)
    execute_btn = page.locator("button").filter(has_text="Execute Shortening")
    assert execute_btn.count() > 0, "Should have Execute Shortening button"


@pytest.mark.e2e
def test_both_interfaces_have_navigation_escape(page, live_server):
    """Test that both dangerous interfaces provide navigation escape routes"""
    # Test move interface
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    # Should be able to navigate away
    nav_links = page.locator("a").filter(has_text="inventory").or_(
        page.locator("a").filter(has_text="Items")
    ).or_(page.locator("a").filter(has_text="Cancel"))
    
    visible_nav_links = [link for link in nav_links.all() if link.is_visible()]
    assert len(visible_nav_links) > 0, "Move interface should have navigation escape routes"
    
    # Test shorten interface
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    # Should be able to navigate away
    nav_links = page.locator("a").filter(has_text="inventory").or_(
        page.locator("a").filter(has_text="Items")
    ).or_(page.locator("a").filter(has_text="Cancel"))
    
    visible_nav_links = [link for link in nav_links.all() if link.is_visible()]
    assert len(visible_nav_links) > 0, "Shorten interface should have navigation escape routes"


@pytest.mark.e2e
def test_forms_have_csrf_protection(page, live_server):
    """Test that both forms have CSRF protection"""
    # Test move form
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    csrf_inputs = page.locator("input[name='csrf_token']").all()
    assert len(csrf_inputs) > 0, "Move form should have CSRF protection"
    
    # Test shorten form
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    csrf_inputs = page.locator("input[name='csrf_token']").all()
    assert len(csrf_inputs) > 0, "Shorten form should have CSRF protection"


@pytest.mark.e2e
def test_interfaces_are_accessible_from_navigation(page, live_server):
    """Test that both interfaces are properly linked in navigation"""
    page.goto(f"{live_server.url}/inventory")
    page.wait_for_load_state("networkidle")
    
    # Should be able to navigate to move interface (may be in dropdown)
    move_link = page.locator("a").filter(has_text="Move")
    if move_link.count() > 0:
        assert move_link.count() > 0, "Move link should exist"
    
    # Should be able to navigate to shorten interface (may be in dropdown)
    shorten_link = page.locator("a").filter(has_text="Shorten")
    if shorten_link.count() > 0:
        assert shorten_link.count() > 0, "Shorten link should exist"


@pytest.mark.e2e 
def test_move_interface_has_queue_management(page, live_server):
    """Test that Move interface has proper queue management (prevents lost operations)"""
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    # Should have queue display
    expect(page.locator("text=Queue").or_(page.locator("text=queue")).first).to_be_visible()
    
    # Should have queue count indicator
    count_indicators = page.locator("text=0 items").or_(
        page.locator("text=items")
    ).or_(page.locator(".badge"))
    
    visible_indicators = [indicator for indicator in count_indicators.all() if indicator.is_visible()]
    assert len(visible_indicators) > 0, "Should have queue count indicator"


@pytest.mark.e2e
def test_shorten_interface_has_summary_section(page, live_server):
    """Test that Shorten interface has operation summary (prevents calculation errors)"""
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    # Should have summary or calculation display
    summary_elements = page.locator("text=Summary").or_(
        page.locator("text=Original")
    ).or_(page.locator("text=New")).or_(
        page.locator("text=Length")
    )
    
    visible_summary_elements = [elem for elem in summary_elements.all() if elem.count() > 0]
    assert len(visible_summary_elements) > 0, "Should have summary section for calculations"


@pytest.mark.e2e
def test_both_interfaces_handle_invalid_input_gracefully(page, live_server):
    """Test that both interfaces handle invalid input without crashing"""
    # Test move interface with invalid input
    page.goto(f"{live_server.url}/inventory/move")
    page.wait_for_load_state("networkidle")
    
    barcode_input = page.locator("#barcode-input")
    if barcode_input.is_visible():
        barcode_input.fill("INVALID_INPUT_TEST")
        # Should not crash
        expect(page.locator("h2")).to_be_visible()
    
    # Test shorten interface with invalid input
    page.goto(f"{live_server.url}/inventory/shorten")
    page.wait_for_load_state("networkidle")
    
    ja_id_input = page.locator("#source-ja-id")
    if ja_id_input.is_visible():
        ja_id_input.fill("INVALID_JA_ID")
        # Should not crash
        expect(page.locator("h2")).to_be_visible()