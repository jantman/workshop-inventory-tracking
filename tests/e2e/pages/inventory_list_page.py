"""
Inventory List Page Object

Page object for the inventory list view functionality.
"""

from .base_page import BasePage
from .inventory_table_mixin import InventoryTableMixin
from playwright.sync_api import expect
from typing import List, Dict


class InventoryListPage(InventoryTableMixin, BasePage):
    """Page object for inventory list view"""
    
    # Selectors
    INVENTORY_TABLE = "table.inventory-table"
    TABLE_ROWS = "tbody tr"
    TABLE_BODY_SELECTOR = "#inventory-table-body"  # Override mixin selector
    TABLE_ROWS_SELECTOR = "#inventory-table-body tr"  # Override mixin selector
    SEARCH_INPUT = "#search-filter"
    FILTER_MATERIAL = "#material-filter"
    FILTER_LOCATION = "#location-filter"  # Note: this doesn't exist in the template
    ADD_ITEM_BUTTON = ".btn-add-item"
    NO_RESULTS_MESSAGE = ".no-results"
    
    def navigate(self):
        """Navigate to inventory list page"""
        self.navigate_to("/inventory")
    
    def wait_for_items_loaded(self):
        """Wait for inventory items to finish loading.

        Settles on any of the three terminal states -- table, empty, or error --
        and then fails loudly if it was the error one. Treating the error state
        as "loaded" and carrying on turns a failed fetch into a 60s timeout on
        whatever row the test looks for next, which says nothing about the cause.
        """
        # Wait for loading spinner to disappear
        loading_state = self.page.locator('#loading-state')
        if loading_state.is_visible():
            expect(loading_state).not_to_be_visible()

        # Wait for table to be visible, or the empty/error state message
        self.page.wait_for_function('''
            () => {
                const table = document.querySelector('#inventory-table-container');
                const emptyState = document.querySelector('#empty-state');
                const errorState = document.querySelector('#error-state');
                return (table && !table.classList.contains('d-none')) ||
                       (emptyState && !emptyState.classList.contains('d-none')) ||
                       (errorState && !errorState.classList.contains('d-none'));
            }
        ''')

        error_state = self.page.locator('#error-state')
        if error_state.count() and not error_state.is_hidden():
            raise AssertionError(
                "Inventory list failed to load: "
                f"{(error_state.text_content() or '').strip()}"
            )
    
    def get_inventory_items(self) -> List[Dict[str, str]]:
        """Get list of inventory items from the table (wrapper for get_table_items)"""
        self.wait_for_element(self.INVENTORY_TABLE)
        return self.get_table_items()
    
    # The list-page filters are applied by onFilterChange(), which filters the
    # already-loaded items in memory and re-renders synchronously -- no debounce
    # and no request. The table is therefore up to date by the time the input
    # event returns, and no wait is needed after any of these.

    def search_items(self, query: str):
        """Perform search in inventory list"""
        if self.is_visible(self.SEARCH_INPUT):
            self.fill_and_wait(self.SEARCH_INPUT, query)

    def filter_by_material(self, material: str):
        """Filter items by material"""
        if self.is_visible(self.FILTER_MATERIAL):
            self.fill_and_wait(self.FILTER_MATERIAL, material)

    def filter_by_location(self, location: str):
        """Filter items by location"""
        if self.is_visible(self.FILTER_LOCATION):
            self.page.select_option(self.FILTER_LOCATION, location)
    
    def click_add_item(self):
        """Click the add item button"""
        if self.is_visible(self.ADD_ITEM_BUTTON):
            self.click_and_wait(self.ADD_ITEM_BUTTON)
    
    def assert_items_displayed(self, expected_count: int):
        """Assert the expected number of items are displayed (wrapper for assert_table_has_rows)"""
        self.assert_table_has_rows(expected_count)

    def assert_item_in_list(self, ja_id: str):
        """Assert that an item with given JA_ID is in the list (wrapper for assert_item_visible)"""
        self.assert_item_visible(ja_id)

    def assert_no_items_displayed(self):
        """Assert no items are displayed (wrapper for assert_table_empty)"""
        if self.is_visible(self.NO_RESULTS_MESSAGE):
            return  # No results message shown
        self.assert_table_empty()
    
    def assert_search_results_contain(self, query: str):
        """Assert search results contain items matching the query"""
        items = self.get_inventory_items()
        matching_items = []
        
        for item in items:
            # Check if query matches any field
            if (query.lower() in item["ja_id"].lower() or
                query.lower() in item["type"].lower() or
                query.lower() in item["shape"].lower() or
                query.lower() in item["material"].lower() or
                query.lower() in item["location"].lower()):
                matching_items.append(item)
        
        assert len(matching_items) > 0, f"No items found matching search query '{query}'"
        return matching_items