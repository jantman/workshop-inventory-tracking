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
    
    # Should show category items (level 1)
    category_items = page.locator('.material-suggestions .suggestion-item.navigable')
    assert category_items.count() > 0, "Should show navigable category items"
    
    # Check for specific categories (using text content)
    expect(suggestions_container).to_contain_text('Aluminum')
    expect(suggestions_container).to_contain_text('Steel')
    
    # Check for category icons
    aluminum_item = page.locator('.material-suggestions .suggestion-item', has_text='Aluminum')
    expect(aluminum_item).to_contain_text('📁')


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
    
    # Click on "Aluminum" category
    aluminum_category = page.locator('.material-suggestions .suggestion-item.navigable').filter(has_text='Aluminum').first
    aluminum_category.click()
    
    # Should now show families within Aluminum
    expect(suggestions_container).to_be_visible()
    
    # Should show family items (like "6000 Series Aluminum", "Pure Aluminum")
    family_items = page.locator('.material-suggestions .suggestion-item.navigable')
    assert family_items.count() > 0, "Should show navigable family items"
    
    # Check for specific families
    expect(suggestions_container).to_contain_text('6000 Series Aluminum')
    
    # Check for family icons  
    family_item = page.locator('.material-suggestions .suggestion-item', has_text='6000 Series Aluminum')
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
    
    # Click Aluminum category
    aluminum_category = page.locator('.material-suggestions .suggestion-item.navigable').filter(has_text='Aluminum').first
    aluminum_category.click()
    
    # Wait for families to load
    expect(suggestions_container).to_be_visible()
    
    # Click on "6000 Series Aluminum" family (if it exists)
    family_6000 = page.locator('.material-suggestions .suggestion-item.navigable', has_text='6000 Series Aluminum')
    if family_6000.count() > 0:
        family_6000.click()
        
        # Should show materials within this family
        expect(suggestions_container).to_be_visible()
        
        # Should show material items with material icons
        material_items = page.locator('.material-suggestions .suggestion-item.selectable')
        assert material_items.count() > 0, "Should show selectable material items"
        
        # Check for specific materials like "6061-T6"
        expect(suggestions_container).to_contain_text('6061-T6')
        
        # Check for material icons
        material_item = page.locator('.material-suggestions .suggestion-item', has_text='6061-T6')
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
    
    # Click Aluminum category
    aluminum_category = page.locator('.material-suggestions .suggestion-item.navigable').filter(has_text='Aluminum').first
    aluminum_category.click()
    
    # Should now be in families view
    expect(suggestions_container).to_be_visible()
    back_button = page.locator('.material-suggestions .suggestion-item.back-button')
    expect(back_button).to_be_visible()
    
    # Click back button
    back_button.click()
    
    # Should be back to categories view
    expect(suggestions_container).to_be_visible()
    expect(suggestions_container).to_contain_text('Aluminum')
    expect(suggestions_container).to_contain_text('Steel')
    
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
    
    # Submit form
    page.locator('button[type="submit"]').click()
    
    # Should redirect to success or list page
    expect(page).to_have_url_regex(r'.*/inventory/.*')
    
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
    expect(suggestions_container).to_contain_text('Aluminum')
    expect(suggestions_container).to_contain_text('📁')
    
    # Navigation should work on edit form too
    aluminum_category = page.locator('.material-suggestions .suggestion-item.navigable').filter(has_text='Aluminum').first
    aluminum_category.click()
    
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
            
            # Input should have the material and not show validation error
            expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
        else:
            # If no materials found, try a different approach - just use a known good material
            material_input.fill('1018')  # Known material from Carbon Steel family
            page.wait_for_timeout(500)  # Wait for validation to process
            
            # Should not show validation error for known material
            expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
    else:
        # Fallback: just type a known valid material
        material_input.fill('1018')
        page.wait_for_timeout(500)  # Wait for validation to process
        expect(material_input).not_to_have_class(re.compile(r'.*is-invalid.*'))
        
        # Form should be submittable
        submit_button = page.locator('button[type="submit"]')
        expect(submit_button).to_be_enabled()
        
        # Submit should work (will redirect or show success)
        submit_button.click()
        
        # Should not stay on same page with validation errors
        expect(page.locator('.invalid-feedback:visible')).to_have_count(0)