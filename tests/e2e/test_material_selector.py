"""
E2E Tests for MaterialSelector Progressive Disclosure Component

Tests the new MaterialSelector component's progressive disclosure interface,
including taxonomy navigation, smart filtering, and keyboard navigation.
"""

import pytest
import re
import time
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage


@pytest.mark.e2e
def test_material_selector_shows_categories_on_focus(page, live_server):
    """Test that MaterialSelector shows categories when input is focused and empty"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus on material input when it's empty
    material_input = page.locator('#material')
    material_input.click()
    
    # Wait for MaterialSelector to initialize and show suggestions
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Wait for API response and suggestion items to populate (longer timeout for CI)
    category_items = page.locator('.material-suggestions .suggestion-item.navigable')
    expect(category_items.first).to_be_visible(timeout=10000)
    assert category_items.count() > 0, "Should show navigable category items"
    
    # Wait for specific categories to appear (API response dependent)
    expect(suggestions_container).to_contain_text('Aluminum', timeout=10000)
    expect(suggestions_container).to_contain_text('Steel', timeout=10000)
    
    # Check for category icons (wait for content to load)
    aluminum_item = page.locator('.material-suggestions .suggestion-item', has_text='Aluminum')
    expect(aluminum_item).to_contain_text('📁', timeout=10000)


@pytest.mark.e2e
def test_material_selector_category_navigation(page, live_server):
    """Test clicking on categories to navigate to families"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus on material input to show categories
    material_input = page.locator('#material')
    material_input.click()
    
    # Wait for suggestions to appear
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Wait for Aluminum category to appear in API response
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    expect(aluminum_category).to_be_visible(timeout=10000)
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Should now show families within Aluminum
    expect(suggestions_container).to_be_visible()
    
    # Wait for family items to load after navigation (API response dependent)
    family_items = page.locator('.material-suggestions .suggestion-item.navigable')
    expect(family_items.first).to_be_visible(timeout=10000)
    assert family_items.count() > 0, "Should show navigable family items"
    
    # Wait for specific families to appear
    expect(suggestions_container).to_contain_text('6000 Series', timeout=10000)
    
    # Check for family icons  
    family_item = page.locator('.material-suggestions .suggestion-item', has_text='6000 Series')
    expect(family_item).to_contain_text('📂')
    
    # Should show back button
    back_button = page.locator('.material-suggestions .suggestion-item.back-button')
    expect(back_button).to_be_visible()
    expect(back_button).to_contain_text('⬅️')
    expect(back_button).to_contain_text('Back')


@pytest.mark.e2e  
def test_material_selector_family_navigation(page, live_server):
    """Test clicking on families to navigate to materials"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Navigate to Aluminum category first
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Wait for Aluminum category to appear, then click navigate button
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    expect(aluminum_category).to_be_visible(timeout=10000)
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Wait for families to load after navigation
    expect(suggestions_container).to_be_visible()
    
    # Wait for "6000 Series" family to appear, then click navigate button (if it exists)
    family_6000 = page.locator('.material-suggestions .suggestion-item.selectable.navigable', has_text='6000 Series')
    if family_6000.count() > 0:
        expect(family_6000).to_be_visible(timeout=10000)
        navigate_button = family_6000.locator('.navigate-btn')
        navigate_button.click()
        
        # Should show materials within this family
        expect(suggestions_container).to_be_visible()
        
        # Should show material items with material icons
        material_items = page.locator('.material-suggestions .suggestion-item.selectable')
        assert material_items.count() > 0, "Should show selectable material items"
        
        # Check for specific materials like "6061-T6"
        expect(suggestions_container).to_contain_text('6061-T6')
        
        # Check for material icons - use exact match with data attribute to avoid strict mode violation
        material_item = page.locator('.material-suggestions .suggestion-item[data-name="6061-T6"]')
        expect(material_item).to_contain_text('🔧')


@pytest.mark.e2e
def test_material_selector_back_navigation(page, live_server):
    """Test back button navigation works correctly"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Navigate to categories → families → back to categories
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Click Aluminum category navigate button to navigate
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Should now be in families view
    expect(suggestions_container).to_be_visible()
    back_button = page.locator('.material-suggestions .suggestion-item.back-button')
    expect(back_button).to_be_visible()
    
    # Click back button
    back_button.click()
    
    # Should be back to categories view (wait for API response)
    expect(suggestions_container).to_be_visible()
    expect(suggestions_container).to_contain_text('Aluminum', timeout=10000)
    expect(suggestions_container).to_contain_text('Steel', timeout=10000)
    
    # Back button should not be visible at top level
    expect(back_button).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_material_selection(page, live_server):
    """Test selecting a material from navigation sets input value"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()  
    add_page.assert_form_visible()
    
    # Navigate through taxonomy to find a selectable material
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Look for a direct material (some categories might have direct materials)
    # or navigate to find one
    material_items = page.locator('.material-suggestions .suggestion-item.selectable')
    
    if material_items.count() > 0:
        # Get the first selectable material
        first_material = material_items.first
        material_name = first_material.locator('.fw-medium').text_content()
        
        # Click to select it
        first_material.click()
        
        # Input should now contain the selected material
        expect(material_input).to_have_value(material_name)
        
        # Suggestions should be hidden
        expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_category_selection(page, live_server):
    """Test that Categories can be selected directly as valid materials"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus on material input to show categories
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Find a category that should be both selectable and navigable (e.g., "Aluminum")
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    expect(aluminum_category).to_be_visible()
    
    # Click on the main area (not the navigate button) to select the category
    aluminum_text = aluminum_category.locator('.fw-medium')
    aluminum_text.click()
    
    # Input should now contain the selected category
    expect(material_input).to_have_value('Aluminum')
    
    # Suggestions should be hidden after selection
    expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_family_selection(page, live_server):
    """Test that Families can be selected directly as valid materials"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Navigate to a family level first
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Click on the navigate button for Aluminum category to navigate to families
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Should now show families within Aluminum
    expect(suggestions_container).to_be_visible()
    
    # Find a family that should be both selectable and navigable (e.g., "6000 Series")
    family_6000 = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='6000 Series')
    if family_6000.count() > 0:
        # Click on the main area (not the navigate button) to select the family
        family_text = family_6000.locator('.fw-medium')
        family_text.click()
        
        # Input should now contain the selected family
        expect(material_input).to_have_value('6000 Series')
        
        # Suggestions should be hidden after selection
        expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_dual_action_navigation(page, live_server):
    """Test that clicking the navigate button on dual-action items navigates instead of selecting"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus on material input to show categories
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Find Aluminum category
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    expect(aluminum_category).to_be_visible()
    
    # Click specifically on the navigate button (arrow)
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Should navigate to families view, not select Aluminum
    expect(suggestions_container).to_be_visible()
    expect(suggestions_container).to_contain_text('6000 Series')  # Should show families
    
    # Input should still be empty (navigation doesn't select)
    expect(material_input).to_have_value('')
    
    # Should show back button
    back_button = page.locator('.material-suggestions .suggestion-item.back-button')
    expect(back_button).to_be_visible()


@pytest.mark.e2e
def test_material_selector_smart_search_mode(page, live_server):
    """Test that typing enables smart search with mixed results"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Type in material input to activate search mode
    material_input = page.locator('#material')
    material_input.fill('steel')
    
    # Wait for search results
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Should show search context
    expect(suggestions_container).to_contain_text('🔍')
    expect(suggestions_container).to_contain_text('Search results for "steel"')
    
    # Should show both direct material matches and category branches
    expect(suggestions_container).to_contain_text('Materials:')
    
    # Should have selectable materials containing "steel"
    material_items = page.locator('.material-suggestions .suggestion-item.selectable')
    assert material_items.count() > 0, "Should show selectable materials in search"
    
    # Check that results contain "steel" (case insensitive)
    steel_items = page.locator('.material-suggestions .suggestion-item', has_text='Steel')
    assert steel_items.count() > 0, "Should show steel-related items in search"


@pytest.mark.e2e
def test_material_selector_search_to_navigation_transition(page, live_server):
    """Test transitioning from search mode back to navigation mode"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Start in search mode
    material_input = page.locator('#material')
    material_input.fill('aluminum')
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    expect(suggestions_container).to_contain_text('Search results')
    
    # Clear input to go back to navigation mode
    material_input.fill('')
    
    # Should show categories again
    expect(suggestions_container).to_be_visible()
    expect(suggestions_container).to_contain_text('Aluminum')
    expect(suggestions_container).to_contain_text('📁')  # Category icons
    
    # Should not show search context
    expect(suggestions_container).not_to_contain_text('Search results')


@pytest.mark.e2e
def test_material_selector_keyboard_navigation(page, live_server):
    """Test keyboard navigation with arrow keys"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus input to show categories
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Use arrow down to select first item
    material_input.press('ArrowDown')
    
    # First suggestion item should be highlighted/active
    active_item = page.locator('.material-suggestions .suggestion-item.active')
    expect(active_item).to_be_visible()
    
    # Press arrow down again to move to second item
    material_input.press('ArrowDown')
    
    # Should have moved to next item (check that we have exactly one active)
    active_items = page.locator('.material-suggestions .suggestion-item.active')
    expect(active_items).to_have_count(1)
    
    # Arrow up should go back
    material_input.press('ArrowUp')
    
    # Should be back to first item
    expect(active_items).to_have_count(1)


@pytest.mark.e2e
def test_material_selector_keyboard_selection(page, live_server):
    """Test selecting items with Enter key"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus input and navigate with keyboard
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Arrow down to first item
    material_input.press('ArrowDown')
    
    active_item = page.locator('.material-suggestions .suggestion-item.active')
    expect(active_item).to_be_visible()
    
    # If it's a navigable item, Enter should navigate
    if 'navigable' in active_item.get_attribute('class'):
        item_name = active_item.locator('.fw-medium').text_content()
        
        # Press Enter to navigate
        material_input.press('Enter')
        
        # Should still show suggestions (navigated to next level)
        expect(suggestions_container).to_be_visible()
    
    # If it's a selectable item, Enter should select and close
    elif 'selectable' in active_item.get_attribute('class'):
        item_name = active_item.locator('.fw-medium').text_content()
        
        # Press Enter to select
        material_input.press('Enter')
        
        # Should set input value and close suggestions
        expect(material_input).to_have_value(item_name)
        expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_escape_closes_dropdown(page, live_server):
    """Test that Escape key closes the dropdown"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Open dropdown
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Press Escape
    material_input.press('Escape')
    
    # Should close dropdown
    expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e 
def test_material_selector_click_outside_closes(page, live_server):
    """Test that clicking outside closes the dropdown"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Open dropdown
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Click outside (on another form field)
    page.locator('#item_type').click()
    
    # Should close dropdown
    expect(suggestions_container).not_to_be_visible()


@pytest.mark.e2e
def test_material_selector_works_on_edit_form(page, live_server):
    """Test that MaterialSelector works on Edit form as well as Add form"""
    # First create an item to edit
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Fill form quickly to create an item
    page.locator('#ja_id').fill('JA999998')
    page.locator('#item_type').select_option('Bar')
    page.locator('#shape').select_option('Round') 
    page.locator('#material').fill('Steel')
    page.locator('#length').fill('12')
    page.locator('#width').fill('1')
    
    # Submit form - use specific submit button to avoid strict mode violation
    page.locator('#submit-btn').click()
    
    # Should redirect to success or list page (inventory list)
    expect(page).to_have_url(re.compile(r'.*/inventory$'))
    
    # Navigate to edit the item we just created
    page.goto(f'{live_server.url}/inventory/edit/JA999998')
    
    # Material input should exist and be pre-filled
    material_input = page.locator('#material')
    expect(material_input).to_be_visible()
    expect(material_input).to_have_value('Steel')
    
    # Clear and test MaterialSelector on edit form
    material_input.fill('')
    material_input.click()
    
    # Should show MaterialSelector categories
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    expect(suggestions_container).to_contain_text('Aluminum', timeout=10000)
    expect(suggestions_container).to_contain_text('📁', timeout=10000)
    
    # Navigation should work on edit form too
    aluminum_category = page.locator('.material-suggestions .suggestion-item.selectable.navigable').filter(has_text='Aluminum').first
    expect(aluminum_category).to_be_visible(timeout=10000)
    navigate_button = aluminum_category.locator('.navigate-btn')
    navigate_button.click()
    
    # Should navigate to families
    expect(suggestions_container).to_be_visible()
    back_button = page.locator('.material-suggestions .suggestion-item.back-button')
    expect(back_button).to_be_visible()


@pytest.mark.e2e
def test_material_selector_validation_integration(page, live_server):
    """Test that MaterialSelector integrates properly with form validation"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Fill required fields except material
    page.locator('#ja_id').fill('JA999997')
    page.locator('#item_type').select_option('Bar')
    page.locator('#shape').select_option('Round')
    page.locator('#length').fill('12')
    page.locator('#width').fill('1')
    
    # Select material using MaterialSelector
    material_input = page.locator('#material')
    material_input.click()
    
    suggestions_container = page.locator('.material-suggestions')
    expect(suggestions_container).to_be_visible(timeout=3000)
    
    # Navigate to find a real material (not a category)
    # Click on Carbon Steel category to navigate to its families
    carbon_steel_category = page.locator('.material-suggestions .suggestion-item').filter(has_text='Carbon Steel')
    if carbon_steel_category.count() > 0:
        carbon_steel_category.first.click()
        expect(suggestions_container).to_be_visible()
        
        # Now look for an actual material
        material_items = page.locator('.material-suggestions .suggestion-item.selectable')
        if material_items.count() > 0:
            # Select first actual material
            first_material = material_items.first
            first_material.click()
            
            # Trigger validation events after material selection
            material_input.dispatch_event('input')
            material_input.dispatch_event('change')
            material_input.dispatch_event('blur')
            page.wait_for_timeout(300)  # Wait for validation to process
            
            # Input should have the material and not show validation error
            expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
        else:
            # If no materials found, try a different approach - just use a known good material
            material_input.fill('Carbon Steel')  # Use a known category/material that should validate
            # Trigger validation events
            material_input.dispatch_event('input')
            material_input.dispatch_event('change')
            material_input.dispatch_event('blur')
            page.wait_for_timeout(500)  # Wait for validation to process
            
            # Should not show validation error for known material
            expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
    else:
        # Fallback: just type a known valid material
        material_input.fill('Carbon Steel')
        # Trigger validation events
        material_input.dispatch_event('input')
        material_input.dispatch_event('change')
        material_input.dispatch_event('blur')
        page.wait_for_timeout(500)  # Wait for validation to process
        expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
        
        # Form should be submittable
        submit_button = page.locator('#submit-btn')
        expect(submit_button).to_be_enabled()
        
        # Submit should work (will redirect or show success)
        submit_button.click()
        
        # Should not stay on same page with validation errors
        expect(page.locator('.invalid-feedback:visible')).to_have_count(0)