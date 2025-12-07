"""
Inventory Table Mixin

Shared test utilities for interacting with the unified inventory table component.
This mixin provides common methods for table interactions used by both the
inventory list and search page objects.
"""

from typing import List, Dict, Optional
from playwright.sync_api import expect


class InventoryTableMixin:
    """Mixin class with common table interaction methods"""

    # Table selectors (override in subclass if different)
    TABLE_BODY_SELECTOR = "#inventory-table-body"
    TABLE_ROWS_SELECTOR = "#inventory-table-body tr"
    TABLE_HEADERS_SELECTOR = "thead th"
    CHECKBOX_ALL_SELECTOR = "#select-all-checkbox"

    def get_table_items(self) -> List[Dict[str, str]]:
        """
        Extract all visible table rows as dictionaries

        Returns:
            List of dictionaries with item data
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute (Playwright page object)")

        rows = self.page.locator(self.TABLE_ROWS_SELECTOR)
        items = []

        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            cells = row.locator("td")

            # Adjust column indices based on whether selection column is present
            has_checkbox = cells.count() >= 10
            offset = 1 if has_checkbox else 0

            item = {
                "ja_id": self._extract_ja_id(cells.nth(offset).text_content() or ""),
                "type": (cells.nth(offset + 1).text_content() or "").strip(),
                "shape": (cells.nth(offset + 2).text_content() or "").strip(),
                "material": (cells.nth(offset + 3).text_content() or "").strip(),
                "dimensions": (cells.nth(offset + 4).text_content() or "").strip(),
                "length": (cells.nth(offset + 5).text_content() or "").strip(),
                "location": (cells.nth(offset + 6).text_content() or "").strip(),
                "status": (cells.nth(offset + 7).text_content() or "").strip(),
            }
            items.append(item)

        return items

    def _extract_ja_id(self, cell_content: str) -> str:
        """Extract JA ID from cell content (may have child/parent info)"""
        lines = cell_content.strip().split('\n')
        return lines[0].strip() if lines else ""

    def sort_by_column(self, column_name: str):
        """
        Click a sortable column header to sort

        Args:
            column_name: Name of column to sort (e.g., "JA ID", "Type", "Material")
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        # Find the header with matching text
        headers = self.page.locator(self.TABLE_HEADERS_SELECTOR)
        count = headers.count()

        for i in range(count):
            header = headers.nth(i)
            if column_name.lower() in (header.text_content() or "").lower():
                # Check if sortable
                if "sortable" in (header.get_attribute("class") or ""):
                    header.click()
                    self.page.wait_for_timeout(500)  # Wait for sort to complete
                    return

        raise ValueError(f"Sortable column '{column_name}' not found")

    def select_item(self, ja_id: str):
        """
        Select an item by checking its checkbox

        Args:
            ja_id: The JA ID of the item to select
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        # Find the row with this JA ID and click its checkbox
        checkbox = self.page.locator(f"input[type='checkbox'][data-ja-id='{ja_id}']")
        if checkbox.count() > 0:
            checkbox.first.check()
            self.page.wait_for_timeout(100)
        else:
            raise ValueError(f"Item {ja_id} not found or doesn't have a checkbox")

    def select_all_items(self):
        """Click the select all button/checkbox"""
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        # Try to find select all button (could be in different places)
        select_all_selectors = [
            "#select-all-btn",
            "#search-select-all-btn",
            self.CHECKBOX_ALL_SELECTOR
        ]

        for selector in select_all_selectors:
            element = self.page.locator(selector)
            if element.count() > 0:
                element.first.click()
                self.page.wait_for_timeout(200)
                return

        raise ValueError("Select all button/checkbox not found")

    def select_none_items(self):
        """Click the select none button"""
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        # Try to find select none button
        select_none_selectors = [
            "#select-none-btn",
            "#search-select-none-btn"
        ]

        for selector in select_none_selectors:
            element = self.page.locator(selector)
            if element.count() > 0:
                element.first.click()
                self.page.wait_for_timeout(200)
                return

        raise ValueError("Select none button not found")

    def get_selected_count(self) -> int:
        """
        Count the number of selected items

        Returns:
            Number of checked checkboxes
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        checked_boxes = self.page.locator("input[type='checkbox'].item-checkbox:checked")
        return checked_boxes.count()

    def click_item_action(self, ja_id: str, action: str):
        """
        Click an action button for a specific item

        Args:
            ja_id: The JA ID of the item
            action: Action name (e.g., "edit", "view", "history", "move", "duplicate")
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        # Find the row with this JA ID
        rows = self.page.locator(self.TABLE_ROWS_SELECTOR)
        count = rows.count()

        for i in range(count):
            row = rows.nth(i)
            if ja_id in (row.text_content() or ""):
                # Find action button within this row
                action_selectors = {
                    "edit": "a[title='Edit'], .btn-outline-primary",
                    "view": "button[title='View Details'], .btn-outline-info",
                    "history": "button[title='View History'], .btn-outline-warning",
                    "move": "a[href*='/inventory/move']",
                    "duplicate": "a[href*='/inventory/duplicate']",
                    "shorten": "a[href*='/inventory/shorten']",
                }

                if action in action_selectors:
                    button = row.locator(action_selectors[action])
                    if button.count() > 0:
                        button.first.click()
                        self.page.wait_for_timeout(500)
                        return

        raise ValueError(f"Action '{action}' not found for item {ja_id}")

    def assert_table_sorted(self, column: str, direction: str = "asc"):
        """
        Verify table is sorted by the specified column

        Args:
            column: Column name to check
            direction: "asc" or "desc"
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        items = self.get_table_items()

        if len(items) < 2:
            return  # Can't verify sort with < 2 items

        # Get values from the specified column
        column_key = column.lower().replace(" ", "_")
        values = [item.get(column_key, "") for item in items]

        # Check if sorted
        if direction == "asc":
            assert values == sorted(values), f"Table not sorted ascending by {column}"
        else:
            assert values == sorted(values, reverse=True), f"Table not sorted descending by {column}"

    def assert_item_visible(self, ja_id: str):
        """
        Assert that an item with the given JA ID is visible in the table

        Args:
            ja_id: The JA ID to look for
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        items = self.get_table_items()
        ja_ids = [item["ja_id"] for item in items]
        assert ja_id in ja_ids, f"Item {ja_id} not visible in table. Found: {ja_ids}"

    def assert_item_not_visible(self, ja_id: str):
        """
        Assert that an item with the given JA ID is NOT visible in the table

        Args:
            ja_id: The JA ID that should not be present
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        items = self.get_table_items()
        ja_ids = [item["ja_id"] for item in items]
        assert ja_id not in ja_ids, f"Item {ja_id} should not be visible in table"

    def assert_column_value(self, ja_id: str, column: str, expected_value: str):
        """
        Verify a specific cell value for an item

        Args:
            ja_id: The JA ID of the item
            column: Column name to check
            expected_value: Expected cell content
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        items = self.get_table_items()

        for item in items:
            if item["ja_id"] == ja_id:
                column_key = column.lower().replace(" ", "_")
                actual_value = item.get(column_key, "")
                assert expected_value.lower() in actual_value.lower(), \
                    f"Item {ja_id} column '{column}' has value '{actual_value}', expected '{expected_value}'"
                return

        raise ValueError(f"Item {ja_id} not found in table")

    def get_table_row_count(self) -> int:
        """
        Get the number of visible rows in the table

        Returns:
            Number of rows
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        rows = self.page.locator(self.TABLE_ROWS_SELECTOR)
        return rows.count()

    def assert_table_has_rows(self, expected_count: Optional[int] = None):
        """
        Assert table has rows (optionally check exact count)

        Args:
            expected_count: If provided, assert exact row count
        """
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        count = self.get_table_row_count()

        if expected_count is not None:
            assert count == expected_count, f"Expected {expected_count} rows, found {count}"
        else:
            assert count > 0, "Table has no rows"

    def assert_table_empty(self):
        """Assert table has no rows"""
        if not hasattr(self, 'page'):
            raise AttributeError("Mixin requires 'page' attribute")

        count = self.get_table_row_count()
        assert count == 0, f"Expected empty table, found {count} rows"
