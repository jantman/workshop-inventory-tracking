"""
Base Page Object Model

Common functionality and patterns shared across all page objects.
"""

from playwright.sync_api import Page, expect
from typing import Optional
import time


class BasePage:
    """Base class for all page objects"""
    
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
    
    def navigate_to(self, path: str = ""):
        """Navigate to a specific path"""
        url = f"{self.base_url}{path}"
        self.page.goto(url)
        self.wait_for_page_load()
    
    def wait_for_page_load(self, timeout: int = 10000):
        """Wait for page to be fully loaded"""
        # Wait for the page to load completely
        self.page.wait_for_load_state("networkidle", timeout=timeout)
        
        # Wait for any loading indicators to disappear
        loading_selectors = [
            ".spinner",
            ".loading",
            "[data-loading]"
        ]
        
        for selector in loading_selectors:
            try:
                self.page.wait_for_selector(selector, state="detached", timeout=2000)
            except:
                pass  # Selector not found or already gone
    
    def wait_for_element(self, selector: str, timeout: int = 10000):
        """Wait for an element to be visible"""
        return self.page.wait_for_selector(selector, timeout=timeout)
    
    def click_and_wait(self, selector: str, wait_for: Optional[str] = None):
        """Click an element and optionally wait for another element"""
        self.page.click(selector)
        if wait_for:
            self.wait_for_element(wait_for)
        else:
            # Default wait for page stability
            time.sleep(0.5)
    
    def fill_and_wait(self, selector: str, value: str):
        """Fill a form field and wait for changes to take effect"""
        self.page.fill(selector, value)
        # Small delay to allow any dynamic updates
        time.sleep(0.2)
    
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
        expect(self.page).to_have_url(f"*{expected_path}*")
    
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