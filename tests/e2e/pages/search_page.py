"""
Search Page Object

Page object for the inventory search functionality.
"""

from .base_page import BasePage
from .inventory_table_mixin import InventoryTableMixin
from playwright.sync_api import expect
from typing import List, Dict


class SearchPage(InventoryTableMixin, BasePage):
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
    WALL_THICKNESS_MIN = "#wall_thickness_min"
    WALL_THICKNESS_MAX = "#wall_thickness_max"

    # Search controls
    SEARCH_BUTTON = "button[type='submit']"
    CLEAR_BUTTON = "#clear-form-btn"
    ADVANCED_SEARCH_TOGGLE = "#advanced-search-toggle"  # This doesn't exist in HTML

    # Results
    RESULTS_TABLE = "#results-table-container .table"
    RESULTS_ROWS = "#results-table-body tr"
    NO_RESULTS = "#no-results"
    RESULTS_COUNT = "#results-count"

    # Override mixin selectors for search page
    TABLE_BODY_SELECTOR = "#results-table-body"
    TABLE_ROWS_SELECTOR = "#results-table-body tr"
    # The search page's spinner has a different id from the list page's. Without
    # this override the mixin's readiness gate would find nothing and silently
    # no-op, which matters for the negative assertions that depend on it.
    LOADING_STATE_SELECTOR = "#search-loading"
    
    def navigate(self):
        """Navigate to search page"""
        self.navigate_to("/inventory/search")
    
    def fill_material(self, material: str) -> None:
        """Type into the material field and dismiss its autocomplete.

        The material input is a MaterialSelector: typing opens a suggestion
        dropdown that overlays the search button, so it has to be closed before
        the search can be clicked.

        Dismissing it is trickier than it looks. MaterialSelector debounces its
        input handler by 200ms, and its keydown handler returns immediately while
        the dropdown is hidden:

            if (!this.suggestionsContainer ||
                this.suggestionsContainer.style.display === 'none') return;

        So pressing Escape straight after fill() lands inside the debounce window,
        is swallowed as a no-op, and does not cancel the pending timer -- the
        dropdown then opens ~200ms later, over the button, after the code meant to
        close it has returned.

        The debounced handler is therefore allowed to run first. It either opens
        the dropdown (dismiss it, and confirm it closed) or leaves it closed
        (nothing to do). The bounded wait below is the one place this file waits
        on a clock: a pending debounce has no observable start, so there is no
        state that distinguishes "has not run yet" from "ran and matched nothing".
        """
        self.fill_and_wait(self.MATERIAL_SEARCH, material)

        suggestions = self.page.locator(".material-suggestions")
        try:
            expect(suggestions.first).to_be_visible(timeout=2000)
        except AssertionError:
            # The debounced handler ran and opened nothing: no matches for this
            # query, so there is no overlay to dismiss.
            return

        self.page.keyboard.press("Escape")
        expect(suggestions.first).not_to_be_visible()

    def search_by_material(self, material: str):
        """Search for items by material"""
        self.fill_material(material)
        self.click_search()

    def search_by_material_with_match_type(self, material: str, exact: bool = False):
        """Search for items by material with exact or contains matching

        Args:
            material: The material name to search for
            exact: If True, use exact match; if False, use contains match (default)
        """
        self.fill_material(material)
        if self.is_visible("#material_exact"):
            self.page.select_option("#material_exact", "true" if exact else "false")
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

    def search_by_active_status(self, active_value: str):
        """Search for items by active/inactive status

        Args:
            active_value: "true" for active items only, "false" for inactive only, "" for all items
        """
        if self.is_visible("#active"):
            self.page.select_option("#active", active_value)
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

    def search_by_length_range(self, length_min: str = None, length_max: str = None):
        """Search for items by length range"""
        if length_min and self.is_visible(self.LENGTH_MIN):
            self.fill_and_wait(self.LENGTH_MIN, length_min)

        if length_max and self.is_visible(self.LENGTH_MAX):
            self.fill_and_wait(self.LENGTH_MAX, length_max)

        self.click_search()

    def search_by_wall_thickness_range(self, wall_thickness_min: str = None, wall_thickness_max: str = None):
        """Search for items by wall thickness range"""
        if wall_thickness_min and self.is_visible(self.WALL_THICKNESS_MIN):
            self.fill_and_wait(self.WALL_THICKNESS_MIN, wall_thickness_min)

        if wall_thickness_max and self.is_visible(self.WALL_THICKNESS_MAX):
            self.fill_and_wait(self.WALL_THICKNESS_MAX, wall_thickness_max)

        self.click_search()

    def search_by_thread_size(self, thread_size: str):
        """Search for items by thread size

        Args:
            thread_size: Thread size to search for (e.g., "1/4-20", "M6x1.0")
        """
        self.fill_and_wait("#thread_size", thread_size)
        self.click_search()

    def search_by_thread_series(self, thread_series: str):
        """Search for items by thread series

        Args:
            thread_series: Thread series to search for (e.g., "UNC", "UNF", "Metric")
        """
        if self.is_visible("#thread_series"):
            self.page.select_option("#thread_series", thread_series)
        self.click_search()

    def click_search(self):
        """Click the search button and wait for the results to render"""
        self.click_and_wait(self.SEARCH_BUTTON)
        self.wait_for_search_complete()

    def wait_for_search_complete(self):
        """Wait until the search has finished and rendered its outcome.

        performSearch() synchronously shows the spinner and hides both result
        panes before it awaits the API, so this cannot pass on the previous
        search's results: it requires the spinner gone *and* one of the two
        outcome panes shown.
        """
        self.page.wait_for_function(
            """() => {
                const hidden = (id) => {
                    const el = document.getElementById(id);
                    return !el || el.classList.contains('d-none');
                };
                return hidden('search-loading')
                    && (!hidden('results-table-container') || !hidden('no-results'));
            }"""
        )

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
                expect(toggle).to_be_checked()
    
    def get_search_results(self) -> List[Dict[str, str]]:
        """Get search results as list of dictionaries (wrapper for get_table_items)"""
        if self.is_visible(self.NO_RESULTS):
            return []

        if not self.is_visible(self.RESULTS_TABLE):
            return []

        return self.get_table_items()
    
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
        """Assert search results contain specific item (wrapper for assert_item_visible)"""
        self.assert_item_visible(ja_id)

    def assert_result_not_contains_item(self, ja_id: str) -> None:
        """Assert search results do NOT contain a specific item.

        Routed through the mixin so the negative assertion gets its readiness
        gate: a results table that has not rendered yet would otherwise satisfy
        "the item is absent" for the wrong reason.
        """
        self.assert_item_not_visible(ja_id)
    
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