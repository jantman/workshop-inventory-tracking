"""
Inventory List Page Object

Page object for the inventory list view functionality.
"""

from .base_page import BasePage
from playwright.sync_api import expect
from typing import List, Dict


class InventoryListPage(BasePage):
    """Page object for inventory list view"""
    
    # Selectors
    INVENTORY_TABLE = "table.inventory-table"
    TABLE_ROWS = "tbody tr"
    SEARCH_INPUT = "#search-input"
    FILTER_MATERIAL = "#filter-material"
    FILTER_LOCATION = "#filter-location"
    ADD_ITEM_BUTTON = ".btn-add-item"
    NO_RESULTS_MESSAGE = ".no-results"
    
    def navigate(self):
        """Navigate to inventory list page"""
        self.navigate_to("/inventory")
    
    def get_inventory_items(self) -> List[Dict[str, str]]:
        """Get list of inventory items from the table"""
        self.wait_for_element(self.INVENTORY_TABLE)
        
        rows = self.page.locator(self.TABLE_ROWS)
        items = []
        
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            cells = row.locator("td")
            
            if cells.count() >= 4:  # Ensure we have enough columns
                item = {
                    "ja_id": cells.nth(0).text_content() or "",
                    "type": cells.nth(1).text_content() or "",
                    "material": cells.nth(2).text_content() or "",
                    "location": cells.nth(3).text_content() or ""
                }
                items.append(item)
        
        return items
    
    def search_items(self, query: str):
        """Perform search in inventory list"""
        if self.is_visible(self.SEARCH_INPUT):
            self.fill_and_wait(self.SEARCH_INPUT, query)
            # Wait for search results to update
            self.page.wait_for_timeout(1000)
    
    def filter_by_material(self, material: str):
        """Filter items by material"""
        if self.is_visible(self.FILTER_MATERIAL):
            self.page.select_option(self.FILTER_MATERIAL, material)
            self.page.wait_for_timeout(1000)
    
    def filter_by_location(self, location: str):
        """Filter items by location"""
        if self.is_visible(self.FILTER_LOCATION):
            self.page.select_option(self.FILTER_LOCATION, location)
            self.page.wait_for_timeout(1000)
    
    def click_add_item(self):
        """Click the add item button"""
        if self.is_visible(self.ADD_ITEM_BUTTON):
            self.click_and_wait(self.ADD_ITEM_BUTTON)
    
    def assert_items_displayed(self, expected_count: int):
        """Assert the expected number of items are displayed"""
        items = self.get_inventory_items()
        assert len(items) == expected_count, f"Expected {expected_count} items, found {len(items)}"
    
    def assert_item_in_list(self, ja_id: str):
        """Assert that an item with given JA_ID is in the list"""
        items = self.get_inventory_items()
        ja_ids = [item["ja_id"] for item in items]
        assert ja_id in ja_ids, f"Item {ja_id} not found in list. Available items: {ja_ids}"
    
    def assert_no_items_displayed(self):
        """Assert no items are displayed (empty list)"""
        if self.is_visible(self.NO_RESULTS_MESSAGE):
            return  # No results message shown
        
        # Check if table is empty
        items = self.get_inventory_items()
        assert len(items) == 0, f"Expected no items, found {len(items)}"
    
    def assert_search_results_contain(self, query: str):
        """Assert search results contain items matching the query"""
        items = self.get_inventory_items()
        matching_items = []
        
        for item in items:
            # Check if query matches any field
            if (query.lower() in item["ja_id"].lower() or
                query.lower() in item["type"].lower() or
                query.lower() in item["material"].lower() or
                query.lower() in item["location"].lower()):
                matching_items.append(item)
        
        assert len(matching_items) > 0, f"No items found matching search query '{query}'"
        return matching_items