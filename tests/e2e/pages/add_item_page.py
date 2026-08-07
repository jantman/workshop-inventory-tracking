"""
Add Item Page Object

Page object for the add inventory item functionality.
"""

import re

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
    VENDOR_PART_NUMBER_INPUT = "#vendor_part_number"
    SUBMIT_BUTTON = "#submit-btn"  # Primary add button
    SUBMIT_AND_CONTINUE_BUTTON = "#submit-and-continue-btn"  # Secondary add & continue button
    CANCEL_BUTTON = ".btn-cancel"
    
    # Form validation
    VALIDATION_ERROR = ".invalid-feedback, .error-message"
    
    def navigate(self):
        """Navigate to add item page"""
        self.navigate_to("/inventory/add")
    
    def fill_basic_item_data(self, ja_id: str, item_type: str, shape: str, material: str):
        """Fill basic required item fields.

        `material` is expected to be a real taxonomy entry -- every caller passes
        one. Tests that deliberately enter an unknown material fill #material
        directly rather than coming through here.
        """
        # The add page fills #ja_id itself, from GET /api/inventory/next-ja-id.
        # Its "only if the field is empty" guard is checked *before* that await
        # and the write lands *after* it, so a fill() issued in the gap has its
        # selection collapsed by the page's write and appends instead of
        # replacing -- leaving "JA000123JA000123", which fails the field's
        # pattern. The browser then refuses the submit, and native constraint
        # validation leaves no trace in the DOM, so the test carries on as though
        # the item exists and fails much later somewhere else.
        #
        # Let the page's own write land first. It is a one-shot on init, so once
        # the field is non-empty nothing else will touch it.
        ja_field = self.page.locator(self.JA_ID_INPUT)
        expect(ja_field).not_to_have_value("")
        self.fill_and_wait(self.JA_ID_INPUT, ja_id)
        expect(ja_field).to_have_value(ja_id)
        self.page.select_option(self.ITEM_TYPE_SELECT, item_type)
        self.page.select_option(self.SHAPE_SELECT, shape)
        self.fill_and_wait(self.MATERIAL_INPUT, material)
        # MaterialValidator calls setCustomValidity(), which makes the whole form
        # fail native validation, until its taxonomy list has arrived. Submitting
        # inside that window is silently refused by the browser and the item is
        # never created.
        #
        # The condition is `is-valid`, not "not is-invalid". validateMaterial()
        # adds is-valid on accept and is-invalid on reject, and *removes both* on
        # an empty field -- so "not is-invalid" is also true of a field the
        # validator has never looked at, and of one something else has since
        # cleared. Only the positive class proves this value was accepted.
        expect(self.page.locator(self.MATERIAL_INPUT)).to_have_class(
            re.compile(r"\bis-valid\b")
        )

    def _fill_if_on_this_form(self, selector: str, value: str):
        """Fill a field that only some variants of the form carry.

        The obvious spelling of this -- `if self.is_visible(sel): fill(sel)` --
        is a snapshot read wrapped in a bare `except: return False`, so on a page
        that has not settled it silently skips a field that is really there. A
        required field left empty that way makes the browser refuse the submit,
        and native constraint validation leaves no trace in the DOM when it does:
        the test carries on as though the item was created and fails much later
        somewhere unrelated. That is how a Print Labels test came to report two
        items where three had been asked for.

        So the question asked here is "is this field part of this form at all",
        which is answered by the served HTML and cannot change under us, and the
        waiting is left to expect().
        """
        field = self.page.locator(selector)
        if field.count() == 0:
            return
        expect(field).to_be_visible()
        field.fill(value)

    def fill_dimensions(self, length: str = None, width: str = None, diameter: str = None):
        """Fill dimension fields"""
        if length:
            self._fill_if_on_this_form(self.LENGTH_INPUT, length)

        if width:
            self._fill_if_on_this_form(self.WIDTH_INPUT, width)

        if diameter:
            self._fill_if_on_this_form(self.DIAMETER_INPUT, diameter)

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
        if location:
            self._fill_if_on_this_form(self.LOCATION_INPUT, location)

        if notes:
            self._fill_if_on_this_form(self.NOTES_INPUT, notes)

    def submit_form(self):
        """Submit the add item form and wait for the server's response to render.

        Returns True if the submission was sent, False if the browser refused it.
        Some callers deliberately submit an incomplete form and check that it was
        refused, so this reports rather than raises.
        """
        return self.submit_and_wait(self.SUBMIT_BUTTON)

    def submit_and_wait(self, button_selector):
        """Click a submit button and wait for the submission to resolve.

        Marks the current document first: a server round trip replaces it, so the
        marker disappearing means the POST completed and the response rendered.
        The alternative -- waiting for an alert to appear -- returns immediately
        whenever the page is already showing one, which lets a test carry on
        before its item exists.

        Client-side validation can also reject the submit without navigating at
        all, and native constraint validation leaves no trace in the DOM when it
        does -- just a browser bubble. The signal for that is the `invalid` event,
        which fires only when the browser actually refuses a submission attempt.

        Testing `form:invalid` instead would be wrong: a form can be invalid
        *before* the click for reasons that are about to clear on their own (the
        material field is marked invalid until MaterialValidator's taxonomy list
        has loaded), so the wait would return immediately having submitted
        nothing, and the caller would carry on as though the item existed.

        Returns True if the submission was sent, False if it was refused. A
        refusal also names the offending fields in the browser console, because
        it is otherwise invisible: the test that carries on regardless fails
        later, somewhere else, for a reason that looks unrelated.
        """
        self.page.evaluate(
            """() => {
                window.__awaitingSubmit = true;
                window.__submitRejected = false;
                // `invalid` does not bubble, so listen in the capture phase.
                document.addEventListener('invalid', (e) => {
                    window.__submitRejected = true;
                    const f = e.target;
                    console.log('E2E: submission refused by #' +
                                (f.id || f.name || '?') + ': ' +
                                (f.validationMessage || 'no message') +
                                ' [value=' + JSON.stringify(f.value) + ']');
                }, true);
            }"""
        )
        self.click_and_wait(button_selector)
        self.page.wait_for_function(
            """() => window.__awaitingSubmit === undefined
                  || window.__submitRejected
                  || !!document.querySelector('.invalid-feedback.d-block')"""
        )
        return self.page.evaluate("() => window.__awaitingSubmit === undefined")


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
    
    def add_minimal_item(self, ja_id: str, material: str = "Carbon Steel", location: str = "Storage A"):
        """Add an item with only required fields"""
        self.fill_basic_item_data(ja_id, "Bar", "Round", material)
        # Bar + Round requires length and width dimensions
        self.fill_dimensions(length="100", width="10")
        # Location is now required (Issue #16)
        self.fill_location_and_notes(location=location)
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
        """Assert the form was submitted successfully.

        submit_form() has already waited for the POST to resolve and the response
        to render, so the outcome is on the page *now* -- either a server-rendered
        success flash or a redirect away from the add form. Reading it directly
        keeps this deterministic. The previous version waited up to 10s for the
        flash and swallowed the timeout, which turned a loaded machine into an
        intermittent failure and hid the real reason when a submit was rejected.
        """
        success_alert = self.page.locator(".alert.alert-success")
        if success_alert.count() > 0:
            return success_alert.first.text_content() or ""

        current_url = self.page.url
        if "/inventory/add" in current_url:
            error_alert = self.page.locator(".alert.alert-danger, .alert.alert-error")
            detail = error_alert.first.text_content() if error_alert.count() else "no error shown"
            raise AssertionError(
                f"Form submission failed - still on add form at {current_url} ({detail.strip()})"
            )
        if "/inventory" in current_url:
            # Redirected to the inventory list: submitted.
            return ""
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
        self.submit_and_wait(self.SUBMIT_AND_CONTINUE_BUTTON)

    def click_carry_forward(self):
        """Click the 'Carry Forward' button"""
        carry_forward_btn = "#carry-forward-btn"
        self.click_and_wait(carry_forward_btn)
        # Carry-forward reports what it did via a toast; the toast arriving is
        # what tells us the fields have finished being populated.
        self.page.wait_for_selector(".toast-body")
    
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