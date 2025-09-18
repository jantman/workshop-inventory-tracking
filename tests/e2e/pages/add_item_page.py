"""
Add Item Page Object

Page object for the add inventory item functionality.
"""

from .base_page import BasePage
from playwright.sync_api import expect


class AddItemPage(BasePage):
    """Page object for add item form"""
    
    # Form selectors
    JA_ID_INPUT = "#ja_id"
    ITEM_TYPE_SELECT = "#item_type"
    SHAPE_SELECT = "#shape"
    MATERIAL_INPUT = "#material"
    LENGTH_INPUT = "#length"
    WIDTH_INPUT = "#width"
    DIAMETER_INPUT = "#diameter"
    THREAD_SERIES_SELECT = "#thread_series"
    THREAD_SIZE_INPUT = "#thread_size"
    THREAD_HANDEDNESS_SELECT = "#thread_handedness"
    LOCATION_INPUT = "#location"
    NOTES_INPUT = "#notes"
    SUBMIT_BUTTON = "#submit-btn"  # Primary add button
    SUBMIT_AND_CONTINUE_BUTTON = "#submit-and-continue-btn"  # Secondary add & continue button
    CANCEL_BUTTON = ".btn-cancel"
    
    # Form validation
    VALIDATION_ERROR = ".invalid-feedback, .error-message"
    
    def navigate(self):
        """Navigate to add item page"""
        self.navigate_to("/inventory/add")
    
    def fill_basic_item_data(self, ja_id: str, item_type: str, shape: str, material: str):
        """Fill basic required item fields"""
        self.fill_and_wait(self.JA_ID_INPUT, ja_id)
        self.page.select_option(self.ITEM_TYPE_SELECT, item_type)
        self.page.select_option(self.SHAPE_SELECT, shape)
        self.fill_and_wait(self.MATERIAL_INPUT, material)
    
    def fill_dimensions(self, length: str = None, width: str = None, diameter: str = None):
        """Fill dimension fields"""
        if length and self.is_visible(self.LENGTH_INPUT):
            self.fill_and_wait(self.LENGTH_INPUT, length)
        
        if width and self.is_visible(self.WIDTH_INPUT):
            self.fill_and_wait(self.WIDTH_INPUT, width)
        
        if diameter and self.is_visible(self.DIAMETER_INPUT):
            self.fill_and_wait(self.DIAMETER_INPUT, diameter)
    
    def fill_thread_information(self, thread_series: str = None, thread_size: str = None, thread_handedness: str = None):
        """Fill thread information fields"""
        if thread_series and self.is_visible(self.THREAD_SERIES_SELECT):
            self.page.select_option(self.THREAD_SERIES_SELECT, thread_series)
        
        if thread_size and self.is_visible(self.THREAD_SIZE_INPUT):
            self.fill_and_wait(self.THREAD_SIZE_INPUT, thread_size)
        
        if thread_handedness and self.is_visible(self.THREAD_HANDEDNESS_SELECT):
            self.page.select_option(self.THREAD_HANDEDNESS_SELECT, thread_handedness)
    
    def fill_location_and_notes(self, location: str = None, notes: str = None):
        """Fill location and notes fields"""
        if location and self.is_visible(self.LOCATION_INPUT):
            self.fill_and_wait(self.LOCATION_INPUT, location)
        
        if notes and self.is_visible(self.NOTES_INPUT):
            self.fill_and_wait(self.NOTES_INPUT, notes)
    
    def submit_form(self):
        """Submit the add item form"""
        self.click_and_wait(self.SUBMIT_BUTTON)
        # Wait a moment for form submission to process
        self.page.wait_for_timeout(1000)
    
    def cancel_form(self):
        """Cancel the add item form"""
        if self.is_visible(self.CANCEL_BUTTON):
            self.click_and_wait(self.CANCEL_BUTTON)
    
    def add_complete_item(self, ja_id: str, item_type: str = "Bar", shape: str = "Round", 
                         material: str = "Carbon Steel", length: str = "1000", 
                         diameter: str = "25", location: str = "Storage A", 
                         notes: str = "Test item"):
        """Add a complete item with all common fields filled"""
        self.fill_basic_item_data(ja_id, item_type, shape, material)
        # For Round shapes, diameter is entered in the width field
        self.fill_dimensions(length=length, width=diameter)
        self.fill_location_and_notes(location=location, notes=notes)
        self.submit_form()
    
    def add_minimal_item(self, ja_id: str, material: str = "Carbon Steel"):
        """Add an item with only required fields"""
        self.fill_basic_item_data(ja_id, "Bar", "Round", material)
        # Bar + Round requires length and width dimensions
        self.fill_dimensions(length="100", width="10")
        self.submit_form()
    
    def assert_form_visible(self):
        """Assert the add item form is visible"""
        self.assert_element_visible(self.JA_ID_INPUT)
        self.assert_element_visible(self.ITEM_TYPE_SELECT)
        self.assert_element_visible(self.SUBMIT_BUTTON)
    
    def assert_validation_error(self, field_selector: str = None):
        """Assert validation error is displayed"""
        if field_selector:
            # Look for error near specific field
            error_selector = f"{field_selector} + {self.VALIDATION_ERROR}, {field_selector} ~ {self.VALIDATION_ERROR}"
            self.assert_element_visible(error_selector)
        else:
            # Look for any validation error
            self.assert_element_visible(self.VALIDATION_ERROR)
    
    def assert_form_submitted_successfully(self):
        """Assert form was submitted successfully (usually redirects or shows success message)"""
        # Check for success flash message or redirect to inventory list
        try:
            self.assert_flash_success()
        except:
            # If no flash message, check if we were redirected to inventory list (not add form)
            current_url = self.page.url
            if "/inventory/add" in current_url:
                # Still on add form - submission likely failed
                raise AssertionError(f"Form submission failed - still on add form at URL: {current_url}")
            elif "/inventory" in current_url:
                # Successfully redirected to inventory list page
                pass
            else:
                # Unexpected redirect location
                raise AssertionError(f"Form submission had unexpected redirect to: {current_url}")
    
    def get_field_value(self, selector: str) -> str:
        """Get the current value of a form field"""
        return self.page.input_value(selector) if self.is_visible(selector) else ""
    
    def assert_field_value(self, selector: str, expected_value: str):
        """Assert a form field has the expected value"""
        actual_value = self.get_field_value(selector)
        assert actual_value == expected_value, f"Field {selector}: expected '{expected_value}', got '{actual_value}'"
    
    def submit_and_continue(self):
        """Submit form using the 'Add & Continue' button"""
        self.click_and_wait(self.SUBMIT_AND_CONTINUE_BUTTON)
        # Wait a moment for form submission to process
        self.page.wait_for_timeout(1000)
    
    def click_carry_forward(self):
        """Click the 'Carry Forward' button"""
        carry_forward_btn = "#carry-forward-btn"
        self.click_and_wait(carry_forward_btn)
        # Wait a moment for data to be populated
        self.page.wait_for_timeout(500)
    
    def assert_carry_forward_success_toast(self):
        """Assert that the carry forward success toast appears"""
        # Look for the success toast message in the toast body
        toast_body_selector = ".toast-body"
        self.page.wait_for_selector(toast_body_selector, timeout=3000)
        toast_text = self.page.locator(toast_body_selector).text_content()
        assert "carried forward" in toast_text.lower() or "previous item data" in toast_text.lower(), f"Expected carry forward success message, got: {toast_text}"
    
    def assert_carry_forward_error_toast(self):
        """Assert that the carry forward error toast appears"""
        # Look for the error/info toast message in the toast body
        toast_body_selector = ".toast-body"
        self.page.wait_for_selector(toast_body_selector, timeout=3000)
        toast_text = self.page.locator(toast_body_selector).text_content()
        assert "No previous item data to carry forward" in toast_text, f"Expected carry forward error message, got: {toast_text}"