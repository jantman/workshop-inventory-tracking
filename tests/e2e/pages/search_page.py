"""
Search Page Object

Page object for the inventory search functionality.
"""

from .base_page import BasePage
from playwright.sync_api import expect
from typing import List, Dict


class SearchPage(BasePage):
    """Page object for inventory search"""
    
    # Search form selectors
    SEARCH_FORM = "#search-form"
    MATERIAL_SEARCH = "#search-material"
    ITEM_TYPE_SEARCH = "#search-item-type"
    LOCATION_SEARCH = "#search-location"
    JA_ID_SEARCH = "#search-ja-id"
    NOTES_SEARCH = "#search-notes"
    LENGTH_MIN = "#length-min"
    LENGTH_MAX = "#length-max"
    DIAMETER_MIN = "#diameter-min"
    DIAMETER_MAX = "#diameter-max"
    
    # Search controls
    SEARCH_BUTTON = "#search-button, .btn-search"
    CLEAR_BUTTON = "#clear-button, .btn-clear"
    ADVANCED_SEARCH_TOGGLE = "#advanced-search-toggle"
    
    # Results
    RESULTS_TABLE = "#search-results"
    RESULTS_ROWS = "#search-results tbody tr"
    NO_RESULTS = ".no-results, .no-search-results"
    RESULTS_COUNT = ".results-count"
    
    def navigate(self):
        """Navigate to search page"""
        self.navigate_to("/inventory/search")
    
    def search_by_material(self, material: str):
        """Search for items by material"""
        self.fill_and_wait(self.MATERIAL_SEARCH, material)
        self.click_search()
    
    def search_by_item_type(self, item_type: str):
        """Search for items by type"""
        if self.is_visible(self.ITEM_TYPE_SEARCH):
            self.page.select_option(self.ITEM_TYPE_SEARCH, item_type)
        self.click_search()
    
    def search_by_location(self, location: str):
        """Search for items by location"""
        self.fill_and_wait(self.LOCATION_SEARCH, location)
        self.click_search()
    
    def search_by_ja_id(self, ja_id: str):
        """Search for items by JA ID"""
        self.fill_and_wait(self.JA_ID_SEARCH, ja_id)
        self.click_search()
    
    def search_by_notes(self, notes_text: str):
        """Search for items by notes content"""
        self.fill_and_wait(self.NOTES_SEARCH, notes_text)
        self.click_search()
    
    def search_by_dimensions(self, length_min: str = None, length_max: str = None,
                           diameter_min: str = None, diameter_max: str = None):
        """Search for items by dimensional ranges"""
        # Enable advanced search if needed
        self.show_advanced_search()
        
        if length_min and self.is_visible(self.LENGTH_MIN):
            self.fill_and_wait(self.LENGTH_MIN, length_min)
        
        if length_max and self.is_visible(self.LENGTH_MAX):
            self.fill_and_wait(self.LENGTH_MAX, length_max)
        
        if diameter_min and self.is_visible(self.DIAMETER_MIN):
            self.fill_and_wait(self.DIAMETER_MIN, diameter_min)
        
        if diameter_max and self.is_visible(self.DIAMETER_MAX):
            self.fill_and_wait(self.DIAMETER_MAX, diameter_max)
        
        self.click_search()
    
    def search_multiple_criteria(self, material: str = None, location: str = None,
                                item_type: str = None, notes: str = None):
        """Search using multiple criteria"""
        if material:
            self.fill_and_wait(self.MATERIAL_SEARCH, material)
        
        if location:
            self.fill_and_wait(self.LOCATION_SEARCH, location)
        
        if item_type and self.is_visible(self.ITEM_TYPE_SEARCH):
            self.page.select_option(self.ITEM_TYPE_SEARCH, item_type)
        
        if notes:
            self.fill_and_wait(self.NOTES_SEARCH, notes)
        
        self.click_search()
    
    def click_search(self):
        """Click the search button"""
        self.click_and_wait(self.SEARCH_BUTTON)
        # Wait for search results to load
        self.page.wait_for_timeout(1500)
    
    def clear_search(self):
        """Clear search form"""
        if self.is_visible(self.CLEAR_BUTTON):
            self.click_and_wait(self.CLEAR_BUTTON)
    
    def show_advanced_search(self):
        """Show advanced search options if hidden"""
        if self.is_visible(self.ADVANCED_SEARCH_TOGGLE):
            toggle = self.page.locator(self.ADVANCED_SEARCH_TOGGLE)
            if not toggle.is_checked():
                toggle.click()
                self.page.wait_for_timeout(500)
    
    def get_search_results(self) -> List[Dict[str, str]]:
        """Get search results as list of dictionaries"""
        if self.is_visible(self.NO_RESULTS):
            return []
        
        if not self.is_visible(self.RESULTS_TABLE):
            return []
        
        rows = self.page.locator(self.RESULTS_ROWS)
        results = []
        
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            cells = row.locator("td")
            
            if cells.count() >= 4:  # Ensure minimum expected columns
                result = {
                    "ja_id": cells.nth(0).text_content() or "",
                    "type": cells.nth(1).text_content() or "",
                    "material": cells.nth(2).text_content() or "",
                    "location": cells.nth(3).text_content() or ""
                }
                results.append(result)
        
        return results
    
    def get_results_count(self) -> int:
        """Get the number of search results"""
        results = self.get_search_results()
        return len(results)
    
    def assert_search_form_visible(self):
        """Assert the search form is visible"""
        self.assert_element_visible(self.SEARCH_FORM)
        self.assert_element_visible(self.SEARCH_BUTTON)
    
    def assert_results_found(self, expected_count: int = None):
        """Assert search results were found"""
        results = self.get_search_results()
        assert len(results) > 0, "No search results found"
        
        if expected_count is not None:
            assert len(results) == expected_count, f"Expected {expected_count} results, found {len(results)}"
    
    def assert_no_results_found(self):
        """Assert no search results were found"""
        if self.is_visible(self.NO_RESULTS):
            return  # No results message displayed
        
        results = self.get_search_results()
        assert len(results) == 0, f"Expected no results, found {len(results)}"
    
    def assert_result_contains_item(self, ja_id: str):
        """Assert search results contain specific item"""
        results = self.get_search_results()
        ja_ids = [result["ja_id"] for result in results]
        assert ja_id in ja_ids, f"Item {ja_id} not found in search results. Found: {ja_ids}"
    
    def assert_all_results_match_criteria(self, material: str = None, location: str = None):
        """Assert all search results match the given criteria"""
        results = self.get_search_results()
        
        for result in results:
            if material:
                assert material.lower() in result["material"].lower(), \
                    f"Result {result['ja_id']} material '{result['material']}' doesn't contain '{material}'"
            
            if location:
                assert location.lower() in result["location"].lower(), \
                    f"Result {result['ja_id']} location '{result['location']}' doesn't contain '{location}'"