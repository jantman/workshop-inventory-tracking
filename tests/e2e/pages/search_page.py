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
    SEARCH_FORM = "#advanced-search-form"
    MATERIAL_SEARCH = "#material"
    ITEM_TYPE_SEARCH = "#item_type"
    SHAPE_SEARCH = "#shape"
    LOCATION_SEARCH = "#location"
    JA_ID_SEARCH = "#ja_id"
    NOTES_SEARCH = "#notes"
    PRECISION_SEARCH = "#precision"
    LENGTH_MIN = "#length_min"
    LENGTH_MAX = "#length_max"
    DIAMETER_MIN = "#width_min"  # Using width as diameter equivalent
    DIAMETER_MAX = "#width_max"
    WIDTH_MIN = "#width_min"
    WIDTH_MAX = "#width_max"
    THICKNESS_MIN = "#thickness_min"
    THICKNESS_MAX = "#thickness_max"

    # Search controls
    SEARCH_BUTTON = "button[type='submit']"
    CLEAR_BUTTON = "#clear-form-btn"
    ADVANCED_SEARCH_TOGGLE = "#advanced-search-toggle"  # This doesn't exist in HTML
    
    # Results
    RESULTS_TABLE = "#results-table-container .table"
    RESULTS_ROWS = "#results-table-body tr"
    NO_RESULTS = "#no-results"
    RESULTS_COUNT = "#results-count"
    
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
    
    def search_by_shape(self, shape: str):
        """Search for items by shape"""
        if self.is_visible(self.SHAPE_SEARCH):
            self.page.select_option(self.SHAPE_SEARCH, shape)
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

    def search_by_precision(self, precision_value: str):
        """Search for items by precision filter

        Args:
            precision_value: "true" for precision items only, "false" for non-precision only, "" for all items
        """
        if self.is_visible(self.PRECISION_SEARCH):
            self.page.select_option(self.PRECISION_SEARCH, precision_value)
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
                                item_type: str = None, shape: str = None, notes: str = None):
        """Search using multiple criteria"""
        if material:
            self.fill_and_wait(self.MATERIAL_SEARCH, material)
        
        if location:
            self.fill_and_wait(self.LOCATION_SEARCH, location)
        
        if item_type and self.is_visible(self.ITEM_TYPE_SEARCH):
            self.page.select_option(self.ITEM_TYPE_SEARCH, item_type)
        
        if shape and self.is_visible(self.SHAPE_SEARCH):
            self.page.select_option(self.SHAPE_SEARCH, shape)
        
        if notes:
            self.fill_and_wait(self.NOTES_SEARCH, notes)
        
        self.click_search()
    
    def search_by_shape_and_width_range(self, shape: str, width_min: str = None, width_max: str = None):
        """Search for items by shape and width range"""
        if shape and self.is_visible(self.SHAPE_SEARCH):
            self.page.select_option(self.SHAPE_SEARCH, shape)

        if width_min and self.is_visible(self.WIDTH_MIN):
            self.fill_and_wait(self.WIDTH_MIN, width_min)

        if width_max and self.is_visible(self.WIDTH_MAX):
            self.fill_and_wait(self.WIDTH_MAX, width_max)

        self.click_search()

    def search_by_thickness_range(self, thickness_min: str = None, thickness_max: str = None):
        """Search for items by thickness range"""
        if thickness_min and self.is_visible(self.THICKNESS_MIN):
            self.fill_and_wait(self.THICKNESS_MIN, thickness_min)

        if thickness_max and self.is_visible(self.THICKNESS_MAX):
            self.fill_and_wait(self.THICKNESS_MAX, thickness_max)

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
            
            if cells.count() >= 7:  # Ensure minimum expected columns (JA ID, Type, Shape, Material, Dimensions, Length, Location, Status, Actions)
                result = {
                    "ja_id": (cells.nth(0).text_content() or "").strip(),      # JA ID - column 0
                    "type": (cells.nth(1).text_content() or "").strip(),       # Type - column 1  
                    "shape": (cells.nth(2).text_content() or "").strip(),      # Shape - column 2
                    "material": (cells.nth(3).text_content() or "").strip(),   # Material - column 3
                    "location": (cells.nth(6).text_content() or "").strip()    # Location - column 6
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
    
    def assert_all_results_match_criteria(self, material: str = None, location: str = None, shape: str = None):
        """Assert all search results match the given criteria"""
        results = self.get_search_results()
        
        for result in results:
            if material:
                assert material.lower() in result["material"].lower(), \
                    f"Result {result['ja_id']} material '{result['material']}' doesn't contain '{material}'"
            
            if location:
                assert location.lower() in result["location"].lower(), \
                    f"Result {result['ja_id']} location '{result['location']}' doesn't contain '{location}'"
            
            if shape:
                assert shape.lower() == result["shape"].lower(), \
                    f"Result {result['ja_id']} shape '{result['shape']}' doesn't match '{shape}'"