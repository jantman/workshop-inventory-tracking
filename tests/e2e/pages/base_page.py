"""
Base Page Object Model

Common functionality and patterns shared across all page objects.
"""

from playwright.sync_api import Page, expect
from typing import Optional
from tests.e2e.debug_utils import E2EDebugCapture


class BasePage:
    """Base class for all page objects"""
    
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
        self._debug_capture: Optional[E2EDebugCapture] = None
    
    def navigate_to(self, path: str = ""):
        """Navigate to a specific path"""
        url = f"{self.base_url}{path}"
        self.page.goto(url)
        self.wait_for_page_load()
    
    def wait_for_page_load(self, timeout: int = 10000):
        """Confirm the document has been parsed.

        page.goto() already waits for the 'load' event, so this is close to free.
        It deliberately does NOT wait for network idle: that costs at least half a
        second on every navigation and tells you nothing about whether the content
        you care about has rendered. Wait for that content with expect() instead.
        """
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

    def wait_for_element(self, selector: str, timeout: int = 10000):
        """Wait for an element to be visible"""
        return self.page.wait_for_selector(selector, timeout=timeout)

    def click_and_wait(self, selector: str, wait_for: Optional[str] = None):
        """Click an element, optionally waiting for another element to appear.

        Playwright's click() already waits for the target to be actionable, so
        there is no unconditional delay here. If the click triggers an async
        update, pass wait_for (or assert on the result with expect()).
        """
        self.page.click(selector)
        if wait_for:
            self.wait_for_element(wait_for)

    def fill_and_wait(self, selector: str, value: str):
        """Fill a form field. Playwright's fill() already waits for actionability."""
        self.page.fill(selector, value)
    
    def get_text(self, selector: str) -> str:
        """Get text content of an element"""
        return self.page.text_content(selector) or ""
    
    def is_visible(self, selector: str) -> bool:
        """Check if an element is visible"""
        try:
            return self.page.is_visible(selector)
        except:
            return False
    
    def screenshot(self, name: str):
        """Take a screenshot for debugging"""
        self.page.screenshot(path=f"screenshots/{name}.png")
    
    def wait_for_flash_message(self, message_type: str = None) -> str:
        """Wait for and return flash message content"""
        if message_type:
            selector = f".alert.alert-{message_type}"
        else:
            selector = ".alert"
        
        element = self.wait_for_element(selector)
        return element.text_content() or ""
    
    def assert_url_contains(self, expected_path: str):
        """Assert that the current URL contains the expected path"""
        current_url = self.page.url
        assert expected_path in current_url, f"Expected '{expected_path}' to be in URL '{current_url}'"
    
    def assert_page_title(self, expected_title: str):
        """Assert the page title"""
        expect(self.page).to_have_title(expected_title)
    
    def assert_element_visible(self, selector: str):
        """Assert an element is visible"""
        expect(self.page.locator(selector)).to_be_visible()
    
    def assert_element_contains_text(self, selector: str, text: str):
        """Assert an element contains specific text"""
        expect(self.page.locator(selector)).to_contain_text(text)
    
    def assert_flash_success(self, expected_message: str = None):
        """Assert a success flash message appears"""
        message = self.wait_for_flash_message("success")
        if expected_message:
            assert expected_message in message, f"Expected '{expected_message}' in flash message, got '{message}'"
        return message
    
    def assert_flash_error(self, expected_message: str = None):
        """Assert an error flash message appears"""
        message = self.wait_for_flash_message("danger")
        if expected_message:
            assert expected_message in message, f"Expected '{expected_message}' in flash message, got '{message}'"
        return message
    
    # Debug utilities
    def setup_debug_capture(self, test_name: str):
        """Set up debug capture for this test"""
        self._debug_capture = E2EDebugCapture(test_name)
        self._debug_capture.setup_page_monitoring(self.page)
        
    def capture_debug_on_failure(self, failure_message: str = ""):
        """Capture debug information when test fails"""
        if self._debug_capture:
            return self._debug_capture.capture_failure_state(self.page, failure_message)
        return None